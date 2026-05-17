"""Tests for the demo-mode rate limiter middleware."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from secondbrain.middleware.rate_limit import RateLimitMiddleware


def _make_app(enabled: bool) -> FastAPI:
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware, enabled=enabled)

    @app.get("/api/v1/ask/stream")
    async def ask_stream() -> dict[str, str]:
        return {"ok": "ask"}

    @app.post("/api/v1/capture")
    async def capture() -> dict[str, str]:
        return {"ok": "capture"}

    @app.get("/api/v1/conversations")
    async def conversations() -> dict[str, str]:
        return {"ok": "convo"}

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"ok": "health"}

    return app


def test_disabled_is_noop_even_past_limits():
    client = TestClient(_make_app(enabled=False))
    # Far exceed the ask limit; with the middleware disabled all should pass.
    responses = [client.get("/api/v1/ask/stream") for _ in range(15)]
    assert all(r.status_code == 200 for r in responses)


def test_ask_limit_enforced():
    client = TestClient(_make_app(enabled=True))
    headers = {"fly-client-ip": "1.2.3.4"}
    for _ in range(10):
        assert client.get("/api/v1/ask/stream", headers=headers).status_code == 200
    resp = client.get("/api/v1/ask/stream", headers=headers)
    assert resp.status_code == 429
    body = resp.json()
    assert "Demo rate limit reached" in body["detail"]
    assert body["retry_after_seconds"] > 0
    assert "Retry-After" in resp.headers


def test_capture_limit_enforced():
    client = TestClient(_make_app(enabled=True))
    headers = {"fly-client-ip": "1.2.3.4"}
    for _ in range(5):
        assert client.post("/api/v1/capture", headers=headers).status_code == 200
    assert client.post("/api/v1/capture", headers=headers).status_code == 429


def test_per_ip_isolation():
    client = TestClient(_make_app(enabled=True))
    # IP A exhausts its ask quota.
    for _ in range(10):
        client.get("/api/v1/ask/stream", headers={"fly-client-ip": "1.1.1.1"})
    assert client.get("/api/v1/ask/stream", headers={"fly-client-ip": "1.1.1.1"}).status_code == 429
    # IP B is unaffected.
    assert client.get("/api/v1/ask/stream", headers={"fly-client-ip": "2.2.2.2"}).status_code == 200


def test_path_class_isolation():
    """Hitting the ask limit must not also exhaust the capture limit for the same IP."""
    client = TestClient(_make_app(enabled=True))
    headers = {"fly-client-ip": "3.3.3.3"}
    for _ in range(10):
        client.get("/api/v1/ask/stream", headers=headers)
    assert client.get("/api/v1/ask/stream", headers=headers).status_code == 429
    # Capture has its own bucket.
    assert client.post("/api/v1/capture", headers=headers).status_code == 200


def test_health_is_bypassed():
    client = TestClient(_make_app(enabled=True))
    headers = {"fly-client-ip": "4.4.4.4"}
    # Even at >60 requests in a minute, /health never rate-limits.
    responses = [client.get("/health", headers=headers) for _ in range(70)]
    assert all(r.status_code == 200 for r in responses)


def test_x_forwarded_for_fallback():
    """When Fly-Client-IP is absent, the first X-Forwarded-For IP is used."""
    client = TestClient(_make_app(enabled=True))
    headers_a = {"x-forwarded-for": "5.5.5.5, 10.0.0.1"}
    headers_b = {"x-forwarded-for": "6.6.6.6, 10.0.0.1"}
    for _ in range(10):
        client.get("/api/v1/ask/stream", headers=headers_a)
    assert client.get("/api/v1/ask/stream", headers=headers_a).status_code == 429
    # Different upstream IP gets its own bucket.
    assert client.get("/api/v1/ask/stream", headers=headers_b).status_code == 200


@pytest.mark.parametrize("path", ["/api/v1/conversations", "/api/v1/wiki"])
def test_default_limit_applies_to_other_paths(path: str):
    """Paths not in the specific list still get the 60/min default limit."""
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware, enabled=True)

    @app.get("/api/v1/conversations")
    async def conversations() -> dict[str, str]:
        return {"ok": "c"}

    @app.get("/api/v1/wiki")
    async def wiki() -> dict[str, str]:
        return {"ok": "w"}

    client = TestClient(app)
    headers = {"fly-client-ip": "7.7.7.7"}
    for _ in range(60):
        assert client.get(path, headers=headers).status_code == 200
    assert client.get(path, headers=headers).status_code == 429
