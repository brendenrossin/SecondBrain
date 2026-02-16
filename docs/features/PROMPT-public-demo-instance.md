# Implementation Prompt: Public Demo Instance

## Feature Spec

Read `docs/features/public-demo-instance.md` for full requirements. This prompt tells you exactly what to build and where.

## Prerequisite

This feature depends on Phase 8.8 (Configurable Categories UI) being complete. The demo should use the generic default categories ("Work" + "Personal"), not the hardcoded AT&T/PwC/Personal categories. If configurable categories aren't done yet, the demo can still be built — just use the generic defaults in the sample vault.

## Implementation Order

1. **WI1: Sample vault** (no dependencies, start immediately)
2. **WI2: Dockerfile** (can parallel with WI1)
3. **WI3: Rate limiting middleware** (independent)
4. **WI4: GitHub Actions deploy pipeline** (depends on WI2)
5. **WI5: README demo link** (depends on WI4 — need the Fly.io URL)

WI1, WI2, and WI3 can all be done in parallel.

---

## WI1: Sample Vault

**Create `demo/vault/` directory tree:**

```
demo/vault/
├── 00_Daily/         # 10-14 daily notes spanning 2 weeks
├── 10_Notes/         # 8-10 notes (recipes, travel, meetings, research)
├── 20_Projects/      # 2-3 project files
├── 30_Concepts/      # 3-4 concept files
├── 90_Meta/
│   └── Templates/    # Daily note template
└── Inbox/            # Empty (captures happen at runtime)
```

**Do NOT commit a `Tasks/` directory** — the task aggregator generates it at build time via `make daily-sync`.

**Fictional persona: "Alex Chen"** — a software engineer at "Meridian Tech" with a side project (a recipe app).

### Daily Notes Format

Follow the existing daily note format from the real vault. Each daily note should have:

```markdown
---
date: 2026-02-03
---

## Events
- 10:30 — Standup
- 14:00 — Design Review

## Tasks
### Work
#### Recipe App
- [ ] Add ingredient search API endpoint (due: 2026-02-07)
- [x] Fix recipe card layout on mobile

#### Platform Migration
- [ ] Document legacy API endpoints (due: 2026-02-05)

### Personal
#### Health
- [ ] Schedule dentist appointment (due: 2026-02-10)

#### Errands
- [x] Pick up dry cleaning

## Focus
- Worked on recipe app API design
- Reviewed Platform Migration RFC

## Notes
- Recipe app users requesting dark mode — add to backlog
```

### Task Design

Tasks should span categories:
- **Work** with sub-projects: "Recipe App" and "Platform Migration"
- **Personal** with subcategories matching defaults: Family, Health, Errands, Projects, General

Include a mix to demonstrate the urgency sorting:
- 3-4 overdue tasks (due dates in the past relative to the latest daily note)
- 2-3 tasks due "today" (same date as the latest daily note)
- 5-6 future tasks
- 4-5 completed tasks (checked off)
- 2-3 tasks with no due date

### Notes Content

Create realistic notes that demonstrate retrieval:
- A recipe note (e.g., "Homemade Pasta Recipe") with ingredients and instructions
- A travel planning note (e.g., "Japan Trip Planning 2026")
- A meeting notes file (e.g., "Platform Migration Kickoff")
- A research note (e.g., "GraphQL vs REST for Recipe App")
- A personal reference note (e.g., "Home Network Setup")

### Project Files

- `20_Projects/Recipe App.md` — side project overview, architecture, tech stack
- `20_Projects/Platform Migration.md` — work initiative, timeline, stakeholders

### Concept Files

- `30_Concepts/API Design Patterns.md` — technical reference
- `30_Concepts/Obsidian Workflow.md` — how Alex uses Obsidian
- `30_Concepts/Meal Prep Guide.md` — personal reference

### Template

Create `90_Meta/Templates/Daily Note Template.md` matching the format used in daily notes.

### Critical: No Real Data

All content must be clearly fictional — no real names, companies, or sensitive data. "Alex Chen" at "Meridian Tech" building a "Recipe App" is the persona throughout.

---

## WI2: Dockerfile

**Create `Dockerfile`** at project root (new file):

Multi-stage build:

### Stage 1: Frontend Build

```dockerfile
FROM node:20-slim AS frontend-build
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
# Override branding for demo
COPY demo/config.ts ./src/lib/config.ts
RUN npm run build
```

### Stage 2: Backend Dependencies

```dockerfile
FROM python:3.12-slim AS backend-build
WORKDIR /app
# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
COPY src/ ./src/
```

### Stage 3: Runtime

```dockerfile
FROM python:3.12-slim AS runtime
WORKDIR /app

# Install Node.js for Next.js runtime
RUN apt-get update && apt-get install -y --no-install-recommends nodejs npm curl && rm -rf /var/lib/apt/lists/*

# Copy backend
COPY --from=backend-build /app/.venv /app/.venv
COPY --from=backend-build /app/src /app/src
COPY --from=backend-build /app/pyproject.toml /app/

# Copy frontend build
COPY --from=frontend-build /app/frontend/.next /app/frontend/.next
COPY --from=frontend-build /app/frontend/public /app/frontend/public
COPY --from=frontend-build /app/frontend/package.json /app/frontend/
COPY --from=frontend-build /app/frontend/node_modules /app/frontend/node_modules
COPY --from=frontend-build /app/frontend/next.config.ts /app/frontend/

# Copy demo vault
COPY demo/vault /vault

# Copy startup script
COPY demo/start.sh /app/start.sh
RUN chmod +x /app/start.sh

# Pre-download sentence-transformers model (420MB — bake into image)
ENV PATH="/app/.venv/bin:$PATH"
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-base-en-v1.5')"

EXPOSE 7860
CMD ["/app/start.sh"]
```

**Create `demo/start.sh`** (new file):

```bash
#!/bin/bash
set -e

export PATH="/app/.venv/bin:$PATH"
export SECONDBRAIN_VAULT_PATH="/vault"
export SECONDBRAIN_DATA_PATH="/data"
export SECONDBRAIN_HOST="0.0.0.0"
export SECONDBRAIN_PORT="8000"
export SECONDBRAIN_DEMO_MODE="true"

# Initialize data directory if empty (first deploy or volume reset)
if [ ! -f /data/documents.db ]; then
    echo "First boot — indexing sample vault..."
    python -m secondbrain.scripts.daily_sync
    echo "Indexing complete."
fi

# Start backend
uvicorn secondbrain.main:app --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!

# Wait for backend to be ready
for i in $(seq 1 30); do
    if curl -s http://localhost:8000/health > /dev/null 2>&1; then
        echo "Backend ready."
        break
    fi
    sleep 1
done

# Start frontend
cd /app/frontend
PORT=7860 npm run start &
FRONTEND_PID=$!

echo "Demo running — frontend on :7860, backend on :8000"

# Wait for either process to exit
wait -n $BACKEND_PID $FRONTEND_PID
```

**Create `demo/config.ts`** (demo branding override — copied over `frontend/src/lib/config.ts` during Docker build):

```typescript
export const APP_NAME = "SecondBrain Demo";
export const USER_NAME = "Alex";
export const USER_INITIAL = "A";
```

**Create `.dockerignore`** (new file):

```
.git
.env
data/
node_modules/
frontend/node_modules/
frontend/.next/
__pycache__
*.pyc
.pytest_cache
.mypy_cache
.ruff_cache
```

### Key details:
- Frontend `next.config.ts` proxy destination stays as `127.0.0.1:8000` (both in same container)
- The data directory `/data` is a Fly.io persistent volume — survives redeployments
- The sentence-transformers model is pre-downloaded in the build stage (avoids 420MB download on first boot)
- API keys are injected via Fly.io secrets, never baked into the image

---

## WI3: Rate Limiting Middleware

**Create `src/secondbrain/middleware/` directory** and `__init__.py`.

**Create `src/secondbrain/middleware/rate_limit.py`** (new file):

```python
"""In-memory rate limiting middleware for the public demo."""

import time
from collections import defaultdict
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

# Rate limit configs: (max_requests, window_seconds)
RATE_LIMITS = {
    "/api/v1/ask": (10, 3600),       # 10 per hour — expensive LLM endpoint
    "/api/v1/capture": (5, 3600),     # 5 per hour — writes to vault
}
DEFAULT_RATE_LIMIT = (60, 60)         # 60 per minute — generous for browsing


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, enabled: bool = False):
        super().__init__(app)
        self.enabled = enabled
        # {(ip, path_prefix): [(timestamp, ...)]
        self.requests: dict[tuple[str, str], list[float]] = defaultdict(list)

    async def dispatch(self, request: Request, call_next):
        if not self.enabled:
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        path = request.url.path

        # Find matching rate limit
        max_requests, window = DEFAULT_RATE_LIMIT
        matched_prefix = ""
        for prefix, limits in RATE_LIMITS.items():
            if path.startswith(prefix):
                max_requests, window = limits
                matched_prefix = prefix
                break

        key = (client_ip, matched_prefix or path)
        now = time.time()

        # Clean old entries
        self.requests[key] = [t for t in self.requests[key] if now - t < window]

        if len(self.requests[key]) >= max_requests:
            oldest = self.requests[key][0]
            retry_after = int(window - (now - oldest)) + 1
            minutes = retry_after // 60
            return JSONResponse(
                status_code=429,
                content={
                    "detail": f"Demo rate limit reached. Try again in {minutes} minute{'s' if minutes != 1 else ''}.",
                    "retry_after": retry_after,
                },
            )

        self.requests[key].append(now)
        return await call_next(request)
```

**Modify `src/secondbrain/config.py`**:
- Add `demo_mode: bool = False` to the `Settings` class (env var: `SECONDBRAIN_DEMO_MODE`)

**Modify `src/secondbrain/main.py`**:
- Import and register the middleware:
  ```python
  from secondbrain.middleware.rate_limit import RateLimitMiddleware

  # After app creation
  settings = get_settings()
  app.add_middleware(RateLimitMiddleware, enabled=settings.demo_mode)
  ```

### Important: No-op when demo_mode is off

When `SECONDBRAIN_DEMO_MODE` is not set (the default), the middleware's `dispatch` immediately calls `call_next(request)` — zero overhead on the real installation.

---

## WI4: GitHub Actions Deploy Pipeline

**Create `.github/workflows/deploy-demo.yml`** (new file):

```yaml
name: Deploy Demo

on:
  push:
    branches: [main]
  workflow_dispatch:  # Allow manual deploy

jobs:
  deploy:
    name: Deploy to Fly.io
    runs-on: ubuntu-latest
    # Only deploy after CI passes
    needs: []  # Add CI job name here if you have one
    steps:
      - uses: actions/checkout@v4

      - uses: superfly/flyctl-actions/setup-flyctl@master

      - run: flyctl deploy --remote-only
        env:
          FLY_API_TOKEN: ${{ secrets.FLY_API_TOKEN }}
```

**Create `fly.toml`** (new file at project root):

```toml
app = "secondbrain-demo"
primary_region = "iad"

[build]

[http_service]
  internal_port = 7860
  force_https = true
  auto_stop_machines = "stop"
  auto_start_machines = true
  min_machines_running = 0

[[vm]]
  size = "shared-cpu-2x"
  memory = "2gb"

[mounts]
  source = "demo_data"
  destination = "/data"

[checks]
  [checks.health]
    type = "http"
    port = 8000
    path = "/health"
    interval = "30s"
    timeout = "5s"
```

### Fly.io Setup (Manual, One-Time)

These steps are done manually, not automated:

1. `fly apps create secondbrain-demo`
2. `fly volumes create demo_data --size 1 --region iad`
3. `fly secrets set SECONDBRAIN_ANTHROPIC_API_KEY=<key> SECONDBRAIN_DEMO_MODE=true`
4. Get API token: `fly tokens create deploy` → add as `FLY_API_TOKEN` GitHub secret
5. Set Anthropic dashboard spending cap to $10/month

---

## WI5: README Demo Link and Badge

**Modify `README.md`** — add near the top, after the project title/description:

```markdown
[![Live Demo](https://img.shields.io/badge/Live_Demo-Try_It-blue)](https://secondbrain-demo.fly.dev)

> **[Try the live demo](https://secondbrain-demo.fly.dev)** — interact with SecondBrain using sample data. No setup required. Uses fictional data; LLM calls are rate-limited.
```

---

## Testing Requirements

**Rate limiter tests** — create `tests/test_rate_limit.py`:
- Rate limit enforced: N+1th request returns 429
- Rate limit not enforced when `enabled=False`
- Different paths have different limits
- Old entries are cleaned up (window expiry)
- Retry-after header is correct

**Docker build test** — add to CI:
- `docker build .` succeeds (validates Dockerfile syntax and dependency resolution)
- Don't run the container in CI — just verify it builds

**Sample vault validation:**
- All daily notes parse correctly (no syntax errors in frontmatter/tasks)
- `make reindex` succeeds against the sample vault (test this manually)

## What's Out of Scope — DO NOT BUILD

- Authentication/login on the demo
- Read-only demo mode (capture is part of the showcase)
- Separate staging environment
- Custom domain
- Docker Compose for local dev
- Vault data persistence across deploys

## Commit Workflow

After implementation: `/test-generation` → `code-simplifier` → commit.
