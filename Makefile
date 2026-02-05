.PHONY: install dev test lint format typecheck check clean

# Install dependencies
install:
	uv sync --all-extras

# Run development server with hot reload
dev:
	uv run uvicorn secondbrain.main:app --reload --host 127.0.0.1 --port 8000

# Run tests
test:
	uv run pytest -v

# Run linter
lint:
	uv run ruff check src tests

# Run formatter
format:
	uv run ruff format src tests

# Run type checker
typecheck:
	uv run mypy src

# Run all checks (lint + typecheck + test)
check: lint typecheck test

# Clean build artifacts
clean:
	rm -rf __pycache__ .pytest_cache .mypy_cache .ruff_cache
	rm -rf src/__pycache__ tests/__pycache__
	rm -rf src/secondbrain/__pycache__
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
