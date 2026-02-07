.PHONY: install dev ui test lint format typecheck check clean index reindex extract process-inbox sync-tasks daily-sync install-cron uninstall-cron install-ui-service uninstall-ui-service eval frontend-install frontend-dev frontend-build dev-all

# Install dependencies
install:
	uv sync --all-extras

# Run FastAPI development server with hot reload
dev:
	uv run uvicorn secondbrain.main:app --reload --host 127.0.0.1 --port 8000

# Run Gradio UI
ui:
	uv run python -m secondbrain.ui

# Index the vault via API (requires running server)
index:
	curl -X POST http://localhost:8000/api/v1/index

# Reindex the vault standalone (no server needed)
reindex:
	uv run python -m secondbrain.scripts.daily_sync index

# Extract metadata from vault notes (requires running server)
extract:
	curl -X POST http://localhost:8000/api/v1/extract

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

# Process inbox notes
process-inbox:
	uv run python -m secondbrain.scripts.daily_sync inbox

# Sync tasks from daily notes
sync-tasks:
	uv run python -m secondbrain.scripts.daily_sync tasks

# Run full daily sync (inbox + tasks + reindex)
daily-sync:
	uv run python -m secondbrain.scripts.daily_sync all

# Install launchd job for daily sync at 7AM
install-cron:
	cp com.secondbrain.daily-sync.plist ~/Library/LaunchAgents/
	launchctl load ~/Library/LaunchAgents/com.secondbrain.daily-sync.plist

# Uninstall launchd job
uninstall-cron:
	launchctl unload ~/Library/LaunchAgents/com.secondbrain.daily-sync.plist 2>/dev/null || true
	rm -f ~/Library/LaunchAgents/com.secondbrain.daily-sync.plist

# Install persistent UI service (auto-start on boot, auto-restart on crash)
install-ui-service:
	kill $$(lsof -ti:7860) 2>/dev/null || true
	sleep 1
	cp com.secondbrain.ui.plist ~/Library/LaunchAgents/
	launchctl load ~/Library/LaunchAgents/com.secondbrain.ui.plist

# Uninstall UI service
uninstall-ui-service:
	launchctl unload ~/Library/LaunchAgents/com.secondbrain.ui.plist 2>/dev/null || true
	rm -f ~/Library/LaunchAgents/com.secondbrain.ui.plist

# Run RAG evaluation harness
eval:
	uv run python -m secondbrain.eval

# Frontend (Next.js)
frontend-install:
	cd frontend && npm install

frontend-dev:
	cd frontend && npm run dev

frontend-build:
	cd frontend && npm run build

# Run FastAPI + Next.js dev servers together
dev-all:
	$(MAKE) dev & $(MAKE) frontend-dev

# Clean build artifacts
clean:
	rm -rf __pycache__ .pytest_cache .mypy_cache .ruff_cache
	rm -rf src/__pycache__ tests/__pycache__
	rm -rf src/secondbrain/__pycache__
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
