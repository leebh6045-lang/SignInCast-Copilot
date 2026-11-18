PYTHON ?= python3
VENV ?= .venv
BIN := $(VENV)/bin

.PHONY: install test lint run run-offline api api-offline verify reset-db tools eval llm-smoke model-eval model-eval-opt smoke record cases demo-hitl actions trace-html clean

install:
	$(PYTHON) -m venv $(VENV)
	$(BIN)/pip install -e ".[dev]"

test:
	$(BIN)/python -m pytest

lint:
	$(BIN)/ruff check app tests eval

run:
	$(BIN)/python -m app.cli

run-offline:
	COPILOT_LLM_PROVIDER=fake $(BIN)/python -m app.cli

api:
	$(BIN)/uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

api-offline:
	COPILOT_LLM_PROVIDER=fake $(BIN)/uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

verify:
	$(BIN)/python -m pytest
	$(BIN)/ruff check app tests eval scripts
	$(BIN)/python -m eval.run_eval

reset-db:
	rm -f data/copilot.db data/copilot.db-wal data/copilot.db-shm

tools:
	$(BIN)/python -m app.cli --list-tools

smoke:
	$(BIN)/python -m app.cli --live --smoke

record:
	$(BIN)/python -m app.cli --record --smoke
	$(BIN)/python scripts/desensitize_fixtures.py
	$(BIN)/python scripts/generate_eval_cases.py

cases:
	$(BIN)/python scripts/generate_eval_cases.py

demo-hitl:
	COPILOT_LLM_PROVIDER=fake $(BIN)/python -m app.cli --sample-fixtures "把这次签到失败的学生补签"
	$(BIN)/python -m app.cli --sample-fixtures --actions

actions:
	$(BIN)/python -m app.cli --actions

eval:
	$(BIN)/python -m eval.run_eval

llm-smoke:
	$(BIN)/python scripts/llm_smoke.py

model-eval:
	$(BIN)/python -m eval.model_eval --verbose \
		--report eval/reports/model-last.json --markdown eval/reports/model-last.md

model-eval-opt:
	$(BIN)/python -m eval.model_eval --rag-top-k 3 --verbose \
		--report eval/reports/optimized.json --markdown eval/reports/optimized.md \
		--baseline eval/reports/baseline.json

trace-html:
	$(BIN)/python -m app.cli --trace-html $(TRACE) $(OUT)

clean:
	rm -rf .pytest_cache .ruff_cache __pycache__ traces
