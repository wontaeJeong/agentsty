.DEFAULT_GOAL := help

.PHONY: help install run lint typecheck test test-unit test-integration test-e2e check

help: ## Show available development commands
	@printf "agentsty developer commands\n\n"
	@awk 'BEGIN {FS = ":.*## "; printf "Usage:\n  make <target>\n\nTargets:\n"} /^[a-zA-Z0-9_.-]+:.*## / {printf "  %-18s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

install: ## Install runtime and development dependencies
	uv sync --dev

run: ## Run the FastAPI application locally
	uv run uvicorn apps.api.main:app --host 127.0.0.1 --port 8000

lint: ## Run Ruff lint checks
	uv run ruff check .

typecheck: ## Run mypy type checks
	uv run mypy src apps tests

test: ## Run the full test suite
	uv run pytest -q

test-unit: ## Run unit tests only
	uv run pytest -q tests/unit

test-integration: ## Run integration tests only
	uv run pytest -q tests/integration

test-e2e: ## Run live-server end-to-end tests only
	uv run pytest -q tests/e2e

check: ## Run lint, type checks, and the full test suite
	uv run ruff check .
	uv run mypy src apps tests
	uv run pytest -q
