PYTHON ?= .venv/bin/python
PIP ?= $(PYTHON) -m pip
PYTEST ?= $(PYTHON) -m pytest
RUFF ?= .venv/bin/ruff
MYPY ?= $(PYTHON) -m mypy

.PHONY: install-dev check-fast test-fast smoke-selfhosted bench

install-dev:
	$(PIP) install -e .[dev,rerank]

check-fast:
	$(RUFF) check .
	$(MYPY) kb_mcp
	$(PYTEST) -q -m "not docker and not benchmark and not external"

test-fast:
	$(PYTEST) -q -m "not docker and not benchmark and not external"

smoke-selfhosted:
	./scripts/release_selfhosted_smoke.sh

bench:
	$(PYTHON) bench/run_benchmark.py --top-k 10 --enforce-gates \
		--metadata-dsn sqlite:///./.kb_mcp/bench_metadata_no_rerank.db \
		--output bench/report_no_rerank.json
	$(PYTHON) bench/run_benchmark.py --top-k 10 --rerank --enforce-gates \
		--metadata-dsn sqlite:///./.kb_mcp/bench_metadata_with_rerank.db \
		--output bench/report_with_rerank.json
