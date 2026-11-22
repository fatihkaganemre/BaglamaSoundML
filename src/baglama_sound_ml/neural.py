"""Small supervised MLP for harmonic envelopes; NumPy-only inference/export."""
from __future__ import annotations
from pathlib import Path
import json
import numpy as np
from .audio import RATE, COURSES, read_wav
from .dataset import load_dataset
from .harmonics import HARMONICS, analyze, features


def train(directory: Path, output: Path, steps: int = 600,
          holdout_variant: str = "karar-G-sharp", seed: int = 7, feedback: dict | None = None) -> dict:
    try:
        import torch
        from torch import nn
    except ImportError as error:
        raise ValueError("Training needs the optional dependency: pip install -e '.[train]'") from error
    if steps < 1:
        raise ValueError("Training steps must be positive.")
    if output.exists():
        raise ValueError("Model already exists; choose a new output filename.")
    torch.manual_seed(seed)
    torch.set_num_threads(1)
    rows = load_dataset(directory)
    training = [r for r in rows if r["variant"] != holdout_variant]
    validation = [r for r in rows if r["variant"] == holdout_variant]
    if not training or not validation:
        raise ValueError("Need both training recordings and a nonempty held-out variant.")
    if any(not any(r["course"] == course for r in training) for course in COURSES):
        raise ValueError("Training must contain all three courses.")
    from .feedback_training import plan_feedback, frame_weights
    feedback_plan=plan_feedback(feedback or {},training,validation)
    def arrays(records, weighted=False):
        inputs, targets, weights = [], [], []
        for row in records:
            audio, rate = read_wav(directory/row["file"])
            if rate != RATE:
                raise ValueError("Training recordings must use 48 kHz.")
            times, amplitudes = analyze(audio, row["frequency_hz"])
            inputs.append(features(row["frequency_hz"], times, row["course"]))
            targets.append(amplitudes)
            weights.append(frame_weights(row,times,feedback_plan) if weighted else np.ones(len(times),dtype=np.float32))
        return np.concatenate(inputs), np.concatenate(targets), np.concatenate(weights)
    x, y, loss_weights = arrays(training,True)
    vx, vy, _ = arrays(validation)
    mean = y.mean(axis=0)
    scale = np.maximum(y.std(axis=0), 0.5)
    xt, yt = torch.from_numpy(x), torch.from_numpy((y-mean)/scale)
    vxt, vyt = torch.from_numpy(vx), torch.from_numpy((vy-mean)/scale)
    log_amplitude_scale = torch.from_numpy(scale)
    # Match the energy trajectory as well as individual partials. Otherwise,
    # quiet harmonics dominate the equally weighted log-amplitude loss.
    render_log_gain = torch.from_numpy(mean.copy())
    render_log_gain[:-1] -= np.log(2) / 2
    render_log_gain[-1] += np.log(0.2)

    def loss_per_frame(predicted, target):
        partial_error = (predicted - target).square().mean(dim=1)
        predicted_power = 2 * (predicted * log_amplitude_scale + render_log_gain)
        target_power = 2 * (target * log_amplitude_scale + render_log_gain)
        envelope_error = (predicted_power.logsumexp(dim=1) - target_power.logsumexp(dim=1)) / 2
        return partial_error + envelope_error.square()

    model = nn.Sequential(nn.Linear(5, 48), nn.SiLU(), nn.Linear(48, 48), nn.SiLU(), nn.Linear(48, HARMONICS+1))
    wt=torch.from_numpy(loss_weights)
    optimizer = torch.optim.Adam(model.parameters(), lr=0.003)
    history, best, weights = [], float("inf"), None
    for step in range(1, steps+1):
        indices = torch.randint(len(xt), (min(512, len(xt)),))
        errors = loss_per_frame(model(xt[indices]), yt[indices])
        loss=(errors*wt[indices]).sum()/wt[indices].sum() if feedback_plan['focuses'] else errors.mean()
        optimizer.zero_grad()
        loss.backward()
        optimizer.step()
        if step == 1 or step % 50 == 0 or step == steps:
            with torch.no_grad():
                val = float(torch.mean((model(vxt)-vyt)**2))
                train_loss = float(torch.mean((model(xt)-yt)**2))
            history.append(dict(step=step, train_normalized_mse=train_loss, validation_normalized_mse=val))
            if val < best:
                best = val
                weights = {k: v.detach().cpu().numpy().copy() for k,v in model.state_dict().items()}
    ranges = {course: [min(r["frequency_hz"] for r in training if r["course"] == course),
                       max(r["frequency_hz"] for r in training if r["course"] == course)] for course in COURSES}
    metadata = dict(schema_version=1, method="pitch-conditioned-harmonic-mlp", seed=seed,
                    analysis="pitch-adaptive-window-dense-attack",
                    training_loss="normalized-log-amplitude-mse-plus-log-rms-mse",
                    training_count=len(training), validation_count=len(validation),
                    holdout_variant=holdout_variant, training_identities=[r["identity"] for r in training],
                    validation_identities=[r["identity"] for r in validation], frequency_ranges_hz=ranges,
                    best_validation_normalized_mse=best, history=history,
                    feedback_training=dict(plan=feedback_plan,weighted_frames=int(np.sum(loss_weights>1)),maximum_weight=float(np.max(loss_weights))),
                    parameters=sum(p.numel() for p in model.parameters()),
                    caveat="Validation variant selects the checkpoint; it is not an independent final test.")
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("wb") as stream:
        np.savez_compressed(stream, **weights, mean=mean, scale=scale, metadata=np.array(json.dumps(metadata)))
    output.with_suffix(".json").write_text(json.dumps(metadata, indent=2)+"\n")
    return metadata


def load_model(path: Path) -> tuple[dict, dict]:
    with np.load(path, allow_pickle=False) as stored:
        weights = {k: stored[k].copy() for k in stored.files if k != "metadata"}
        metadata = json.loads(str(stored["metadata"]))
    if metadata.get("schema_version") != 1:
        raise ValueError("Unsupported model version.")
    return weights, metadata


def predict(weights: dict, inputs: np.ndarray) -> np.ndarray:
    value = inputs
    for layer in (0, 2, 4):
        value = value @ weights[f"{layer}.weight"].T + weights[f"{layer}.bias"]
        if layer != 4:
            value = value / (1+np.exp(-np.clip(value, -60, 60)))
    return np.exp(np.clip(value*weights["scale"] + weights["mean"], -14, 0))
