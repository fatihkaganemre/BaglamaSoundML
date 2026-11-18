#!/bin/sh
set -eu
TASK_PROJECT_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$TASK_PROJECT_ROOT"
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH=src
TASK_PYTHON="$TASK_PROJECT_ROOT/.venv/bin/python3"
if [ ! -x "$TASK_PYTHON" ]; then
  echo "Missing project Python environment. Create .venv and install the project dependencies first." >&2
  exit 1
fi
if ! "$TASK_PYTHON" -c 'import numpy' >/dev/null 2>&1; then
  echo "NumPy is missing from the project environment. Run: .venv/bin/python3 -m pip install -e '.[train]'" >&2
  exit 1
fi
exec "$TASK_PYTHON" -u -m baglama_sound_ml serve "$@"
