"""In-memory IP-based rate limiter for the public demo instance.

Active only when ``settings.demo_mode`` is true. Tracks request timestamps in
a per-(IP, limit-class) sliding window. Single-process; resets when the
container restarts, which is acceptable for the demo.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse, Response

# (path-prefix, max_requests, window_seconds). First match wins.
_PATH_LIMITS: tuple[tuple[str, int, int], ...] = (
    ("/api/v1/ask/stream", 10, 3600),
    ("/api/v1/ask", 10, 3600),
    ("/api/v1/capture", 5, 3600),
)
# Catch-all for any other path
_DEFAULT_LIMIT: tuple[int, int] = (60, 60)

# Paths that never count toward rate limits (health checks, polling).
_BYPASS_PATHS: frozenset[str] = frozenset({"/health", "/api/v1/health", "/"})


def _client_ip(request: Request) -> str:
    """Best-effort real client IP behind Fly.io / generic proxies."""
    fly_ip = request.headers.get("fly-client-ip")
    if fly_ip:
        return fly_ip
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _match_limit(path: str) -> tuple[int, int]:
    for prefix, max_req, window in _PATH_LIMITS:
        if path.startswith(prefix):
            return max_req, window
    return _DEFAULT_LIMIT


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Sliding-window per-IP rate limiter, gated by ``enabled``."""

    def __init__(self, app: object, enabled: bool = True) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self.enabled = enabled
        self._buckets: dict[tuple[str, str], deque[float]] = defaultdict(deque)

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if not self.enabled:
            return await call_next(request)

        path = request.url.path
        if path in _BYPASS_PATHS:
            return await call_next(request)

        max_req, window = _match_limit(path)
        ip = _client_ip(request)
        bucket_key = (ip, f"{max_req}:{window}")
        now = time.monotonic()

        bucket = self._buckets[bucket_key]
        while bucket and bucket[0] < now - window:
            bucket.popleft()

        if len(bucket) >= max_req:
            retry_after = max(1, int(bucket[0] + window - now))
            minutes = max(1, retry_after // 60)
            return JSONResponse(
                status_code=429,
                content={
                    "detail": (f"Demo rate limit reached. Try again in {minutes} minute(s)."),
                    "retry_after_seconds": retry_after,
                },
                headers={"Retry-After": str(retry_after)},
            )

        bucket.append(now)
        return await call_next(request)
