.PHONY: up down logs test bench bench-report demo-build

up: ## start LiteLLM + analyzer + anonymizer + demo
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f --tail=100

# --- analyzer unit tests (checksums, recognizers) in the bench venv
test:
	cd bench && . .venv/bin/activate && cd ../analyzer && python -m pytest -q

# --- benchmarks: all datasets, fast detectors by default; DETECTORS=... to pick
DETECTORS ?= rules,spacy-lg
DATASETS ?= pii-bench,jayguard,redmadrobot,synthetic,secrets
bench:
	cd bench && . .venv/bin/activate && HF_HOME=$$PWD/.cache/hf python -m buffbench.run run --detectors $(DETECTORS) --datasets $(DATASETS)

bench-report:
	cd bench && . .venv/bin/activate && python -m buffbench.run report results/raw/*.json > results/RESULTS.md && cat results/RESULTS.md

bench-venv:
	cd bench && python3 -m venv .venv && . .venv/bin/activate && pip install -q --upgrade pip \
	  && pip install -q torch --index-url https://download.pytorch.org/whl/cpu \
	  && pip install -q -e ../analyzer[hf,gliner,test] gliner2 datasets faker spacy pyyaml \
	  && for m in ru_core_news_lg en_core_web_lg ru_core_news_sm en_core_web_sm; do python -m spacy download -q $$m; done
