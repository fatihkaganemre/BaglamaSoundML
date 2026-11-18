.DEFAULT_GOAL := help
PORT ?= 8765
STEPS ?= 600
SEED ?= 7
FEEDBACK ?= 1
PYTHON := .venv/bin/python3
export PYTHONDONTWRITEBYTECODE := 1

.PHONY: help start stop restart train compare test evaluate-final-tone
help:
	@echo 'BaglamaSoundML commands:'
	@echo '  make help     Show this list (also the default for make)'
	@echo '  make start    Start with the latest successful model'
	@echo '  make stop     Stop this project app'
	@echo '  make restart Restart with the latest successful model'
	@echo '  make train    Export library, prepare dataset, train, and compare'
	@echo '  make compare  Open the latest listening comparison'
	@echo '  make evaluate-final-tone  Evaluate saved strum labels (never trains)'
	@echo '  make test     Run Python regression tests'
	@echo 'Options: PORT=8766; training: STEPS=1200 SEED=7 FEEDBACK=0 (real-only control)'
	@echo 'Workflow and setup: COMMANDS.md'
start:
	@$(PYTHON) scripts/app.py start --port $(PORT)
stop:
	@./scripts/listen.sh --stop --port $(PORT)
restart:
	@$(PYTHON) scripts/app.py restart --port $(PORT)
train:
	@./scripts/retrain.sh --steps $(STEPS) --seed $(SEED) --port $(PORT) $(if $(filter 0,$(FEEDBACK)),--no-feedback,)
compare:
	@$(PYTHON) scripts/app.py compare --port $(PORT)
test:
	@PYTHONPATH=src $(PYTHON) -m unittest discover -s tests -v

evaluate-final-tone:
	@$(PYTHON) scripts/evaluate-final-tone.py
