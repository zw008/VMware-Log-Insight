"""Connection-layer error translation + recovery (踩坑 #37).

Uses httpx.MockTransport so no live appliance is needed. Pins: 404 -> teaching
LogInsightApiError, transient 503 retried exactly once, 401 -> single re-auth,
transport error -> LogInsightApiError with status_code None, is_alive semantics.
"""

from __future__ import annotations

import time
from types import SimpleNamespace

import httpx
import pytest

from vmware_log_insight.connection import LogInsightApiError, LogInsightClient


def _client(handler) -> LogInsightClient:
    """Build a client wired to a MockTransport, bypassing real network auth."""
    c = LogInsightClient.__new__(LogInsightClient)
    # Minimal target so the re-auth path (reads username/provider) works.
    c._target = SimpleNamespace(username="u", provider="Local", host="li.test")
    c._base_url = "https://li.test:9543/api/v2"
    c._password = "pw"
    c._session_id = "sess"
    c._session_expires_at = time.time() + 9999
    c._liveness_checked_at = 0.0
    c._client = httpx.Client(base_url=c._base_url, transport=httpx.MockTransport(handler))
    return c


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda *_a, **_k: None)


def test_404_raises_teaching_error():
    c = _client(lambda req: httpx.Response(404, json={}))
    with pytest.raises(LogInsightApiError) as ei:
        c.get("/alerts/does-not-exist")
    assert ei.value.status_code == 404
    assert "list the parent collection" in str(ei.value)


def test_503_retried_exactly_once_then_raises():
    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        return httpx.Response(503, json={})

    c = _client(handler)
    with pytest.raises(LogInsightApiError) as ei:
        c.get("/fields")  # default retries=1
    assert ei.value.status_code == 503
    assert calls["n"] == 2  # original + one retry


def test_401_triggers_single_reauth_then_succeeds():
    state = {"events_calls": 0}

    def handler(req):
        if req.url.path.endswith("/sessions"):
            return httpx.Response(200, json={"sessionId": "new", "ttl": 1800})
        state["events_calls"] += 1
        # First events call 401s; after re-auth the retry succeeds.
        if state["events_calls"] == 1:
            return httpx.Response(401, json={})
        return httpx.Response(200, json={"events": []})

    c = _client(handler)
    out = c.get("/events/timestamp/LAST/3600000")
    assert out == {"events": []}
    assert state["events_calls"] == 2


def test_transport_error_becomes_apierror_without_status():
    def handler(req):
        raise httpx.ConnectError("connection refused")

    c = _client(handler)
    with pytest.raises(LogInsightApiError) as ei:
        c.get("/fields")
    assert ei.value.status_code is None
    assert "could not connect" in str(ei.value)


def test_is_alive_true_on_503_false_on_401():
    assert _client(lambda r: httpx.Response(503, json={})).is_alive() is True
    assert _client(lambda r: httpx.Response(401, json={})).is_alive() is False
