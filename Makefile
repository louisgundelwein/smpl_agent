VENV   := .venv
PYTHON := $(VENV)/bin/python
PIP    := $(PYTHON) -m pip

# ── Setup ────────────────────────────────────────────────────────────────────

.PHONY: setup
setup: ## Create venv + install all dependencies (run this first)
	python3 -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -e ".[dev]"
	@echo "\n✓ Done. Activate with: source $(VENV)/bin/activate"

.PHONY: setup-transcription
setup-transcription: ## Install optional Whisper transcription deps
	$(PIP) install -e ".[dev,transcription]"

.PHONY: install
install: ## Re-install dependencies (venv must exist)
	$(PIP) install -e ".[dev]"

# ── Database ──────────────────────────────────────────────────────────────────

.PHONY: migrate
migrate: ## Run all migrations against DATABASE_URL from .env
	@export $$(grep -v '^#' .env | xargs) && \
	  psql $$DATABASE_URL -f migrations/001_initial.sql && \
	  echo "✓ Migration 001 done" && \
	  psql $$DATABASE_URL -f migrations/003_fix_memories_vector_1024.sql && \
	  echo "✓ Migration 003 done (vector 1024 + conversations)"

.PHONY: migrate-fix
migrate-fix: ## Fix memories table: vector(3072)→1536 (migration 002, legacy)
	@export $$(grep -v '^#' .env | xargs) && \
	  psql $$DATABASE_URL -f migrations/002_fix_memories_vector_dimensions.sql && \
	  echo "✓ Migration 002 done"

# ── Run ──────────────────────────────────────────────────────────────────────

.PHONY: run
run: ## Start the interactive terminal REPL
	$(PYTHON) -m src.main

.PHONY: serve
serve: ## Start in daemon/server mode
	$(PYTHON) -m src.main serve

.PHONY: start
start: ## Start background daemon
	$(PYTHON) -m src.main start

.PHONY: stop
stop: ## Stop background daemon
	$(PYTHON) -m src.main stop

.PHONY: status
status: ## Show daemon status
	$(PYTHON) -m src.main status

# ── Tests ─────────────────────────────────────────────────────────────────────

.PHONY: test
test: ## Run full test suite
	$(VENV)/bin/pytest tests/ -v

.PHONY: test-watch
test-watch: ## Run tests in watch mode (requires pytest-watch)
	$(VENV)/bin/ptw tests/ -- -v

# ── Helpers ──────────────────────────────────────────────────────────────────

.PHONY: help
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*##' $(MAKEFILE_LIST) | \
	  awk 'BEGIN {FS = ":.*##"}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

.DEFAULT_GOAL := help
