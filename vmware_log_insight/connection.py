"""Log Insight (Aria Operations for Logs) REST client with session auth.

Authenticates via ``POST /api/v2/sessions`` with username/password/provider and
carries the returned ``sessionId`` as ``Authorization: Bearer <sessionId>`` on
subsequent calls. The session has a TTL (seconds); it is re-acquired
automatically near expiry.

Per CLAUDE.md 踩坑 #37, HTTP error codes are translated to a teaching
``LogInsightApiError`` in ONE place (``_request``), so callers never surface a
raw httpx traceback: transient gateway errors (502/503/504) and transport
failures get one light retry, a 401 triggers a single re-auth, and 4xx client
errors (e.g. 404 for a bad alert id) are not retried.

Base URL pattern: https://<host>:<port>/api/v2  (default port 9543)
"""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from vmware_log_insight.config import AppConfig, TargetConfig, load_config

_log = logging.getLogger("vmware-log-insight.connection")

# Refresh the session this many seconds before its TTL actually expires.
_EXPIRY_BUFFER_SEC = 60

# Transient gateway statuses worth one automatic retry. 4xx are NOT retried.
_TRANSIENT_STATUS = frozenset({502, 503, 504})
_RETRY_DELAY_SEC = 2.0

# Trust a successful liveness probe for this long so a burst of connect() calls
# doesn't re-probe GET /sessions/current every time.
_LIVENESS_TTL_SEC = 30.0

# Fallback session lifetime if the server omits ttl (Log Insight default ~30 min).
_DEFAULT_TTL_SEC = 1800


class LogInsightApiError(Exception):
    """A Log Insight API call returned an error or failed to connect.

    Carries a teaching message (status + path + how to fix). ``status_code`` is
    None for transport/timeout failures (no HTTP response was received).
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        method: str | None = None,
        path: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.method = method
        self.path = path


def _hint_for_status(status_code: int, path: str) -> str:
    """Return a short, actionable remediation hint for an HTTP error status."""
    if status_code == 404:
        return (
            f"Nothing exists at {path}. Check the id — list the parent collection "
            "first (e.g. `alert list`) and copy an exact id."
        )
    if status_code == 400:
        return (
            "Bad request — check the query constraints and parameters. Time/field "
            "constraints are path-encoded as field/OPERATOR/value segments."
        )
    if status_code in (401, 403):
        return "Authentication/authorization failed — check the account, password, and provider."
    if status_code == 503:
        return "The appliance is starting up or a service is not ready. Wait and retry."
    if status_code in (502, 504):
        return "The node is busy or a gateway timed out — retry shortly."
    if status_code >= 500:
        return "Server-side error — retry shortly; check Log Insight health."
    return "Check the request and try again."


class LogInsightClient:
    """REST client for a single Log Insight instance."""

    def __init__(self, target: TargetConfig, password: str) -> None:
        self._target = target
        self._base_url = f"https://{target.host}:{target.port}/api/v2"
        self._password = password
        self._session_id: str | None = None
        self._session_expires_at: float = 0.0
        self._liveness_checked_at: float = 0.0

        if not target.verify_ssl:
            import urllib3

            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

        self._client = httpx.Client(
            base_url=self._base_url,
            verify=target.verify_ssl,
            timeout=30.0,
        )
        self._acquire_session()

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    def _acquire_session(self) -> None:
        """Acquire a new sessionId from Log Insight.

        Auth errors are translated to ``LogInsightApiError`` here (this runs at
        connect time and on mid-request refresh), so a wrong password (401),
        bad provider (400), or a booting appliance (503) surfaces a teaching
        message instead of a raw httpx traceback.
        """
        payload = {
            "username": self._target.username,
            "password": self._password,
            "provider": self._target.provider,
        }
        try:
            resp = self._client.post(
                "/sessions", json=payload, headers={"Accept": "application/json"}
            )
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            if status in (400, 401, 403):
                hint = (
                    "Check username/password/provider in "
                    "~/.vmware-log-insight/config.yaml and the password env var in "
                    "~/.vmware-log-insight/.env."
                )
            else:
                hint = _hint_for_status(status, "/sessions")
            raise LogInsightApiError(
                f"Log Insight authentication to {self._target.host} failed: "
                f"POST /sessions returned HTTP {status}. {hint}",
                status_code=status,
                method="POST",
                path="/sessions",
            ) from exc
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            raise LogInsightApiError(
                f"Log Insight authentication to {self._target.host} could not "
                f"connect: {exc}. Check the host/port and network, then retry.",
                method="POST",
                path="/sessions",
            ) from exc

        data = resp.json()
        session_id = data.get("sessionId")
        if not session_id:
            raise ConnectionError(
                "Log Insight session acquisition succeeded but no sessionId returned"
            )
        # ttl is a duration in SECONDS (not an epoch). Default ~30 min if absent.
        ttl = data.get("ttl") or _DEFAULT_TTL_SEC
        self._session_id = session_id
        self._session_expires_at = time.time() + float(ttl)
        _log.info(
            "Log Insight session acquired for %s (ttl %.0fs)",
            self._target.host,
            float(ttl),
        )

    def _ensure_session(self) -> None:
        """Re-acquire the session if expired or near expiry."""
        if time.time() >= (self._session_expires_at - _EXPIRY_BUFFER_SEC):
            _log.info("Session expired or near expiry, re-acquiring...")
            self._acquire_session()

    def _headers(self) -> dict[str, str]:
        self._ensure_session()
        return {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._session_id}",
        }

    # ------------------------------------------------------------------
    # HTTP
    # ------------------------------------------------------------------

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_data: dict[str, Any] | None = None,
        retries: int = 1,
    ) -> httpx.Response:
        """Send one request, recovering from auth and transient failures.

        Layered per the error-recovery contract: (1) transport/timeout and
        transient gateway statuses (502/503/504) are retried once after a short
        delay; (2) a 401/403 triggers a single session re-acquisition (the
        re-issue goes back through the top of the loop so it is covered by the
        same transport-error handling); (3) any remaining error status is
        translated to a teaching ``LogInsightApiError``. 4xx client errors
        (e.g. 404 for a bad id) are NOT retried.
        """
        attempt = 0
        reauthed = False
        while True:
            try:
                resp = self._client.request(
                    method, path, headers=self._headers(), params=params, json=json_data
                )
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                if attempt < retries:
                    attempt += 1
                    time.sleep(_RETRY_DELAY_SEC)
                    continue
                raise LogInsightApiError(
                    f"Log Insight {method} {path} could not connect: {exc}. "
                    "Check the host/port and network, then retry.",
                    method=method,
                    path=path,
                ) from exc

            if resp.status_code in (401, 403) and not reauthed:
                _log.info("Auth error on %s %s, re-acquiring session...", method, path)
                self._acquire_session()
                reauthed = True
                continue

            if resp.status_code in _TRANSIENT_STATUS and attempt < retries:
                attempt += 1
                time.sleep(_RETRY_DELAY_SEC)
                continue

            if resp.status_code >= 400:
                raise LogInsightApiError(
                    f"Log Insight {method} {path} returned HTTP "
                    f"{resp.status_code}. {_hint_for_status(resp.status_code, path)}",
                    status_code=resp.status_code,
                    method=method,
                    path=path,
                )
            return resp

    def get(self, path: str, params: dict[str, Any] | None = None, *, retries: int = 1) -> dict:
        """Single GET request. Returns parsed JSON (or {} for an empty body).

        Pass retries=0 for probes where an error status is itself the answer
        (e.g. a liveness check) to skip the transient back-off.
        """
        resp = self._request("GET", path, params=params, retries=retries)
        return resp.json() if resp.content else {}

    def is_alive(self) -> bool:
        """Check whether the cached client + session are still usable.

        A reachable appliance that returns 5xx (e.g. 503 while a service boots)
        is still "alive": the client and session work, the platform just isn't
        ready, so there's no point rebuilding the connection. Only auth failures
        (401/403) or transport errors mean the cached client is stale.
        """
        try:
            self._request("GET", "/sessions/current", retries=0)
            self._liveness_checked_at = time.time()
            return True
        except LogInsightApiError as exc:
            return exc.status_code is not None and exc.status_code not in (401, 403)
        except Exception:
            return False

    def is_alive_cached(self, ttl: float = _LIVENESS_TTL_SEC) -> bool:
        """Liveness check that skips the HTTP probe within ``ttl`` of the last success."""
        if self._liveness_checked_at and (time.time() - self._liveness_checked_at) < ttl:
            return True
        return self.is_alive()

    def close(self) -> None:
        """Close the HTTP client.

        Log Insight sessions expire on their own TTL, and the public v2 API has
        no verified session-delete endpoint, so we simply drop the local session
        and close the connection pool rather than calling an unconfirmed logout
        path (踩坑 #36 — no hallucinated endpoints).
        """
        self._session_id = None
        self._client.close()


class ConnectionManager:
    """Manages connections to multiple Log Insight targets."""

    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._clients: dict[str, LogInsightClient] = {}

    @classmethod
    def from_config(cls, config: AppConfig | None = None) -> ConnectionManager:
        return cls(config or load_config())

    def connect(self, target_name: str | None = None) -> LogInsightClient:
        """Get or create a LogInsightClient for the specified target."""
        name = target_name or self._config.default_target
        if not name:
            raise ValueError("No target specified and no default target configured")

        if name in self._clients:
            if self._clients[name].is_alive_cached():
                return self._clients[name]
            self._clients[name].close()
            del self._clients[name]

        target_cfg = self._config.get_target(name)
        if target_cfg is None:
            available = ", ".join(self._config.targets.keys())
            raise ValueError(f"Target '{name}' not found. Available: {available}")

        client = LogInsightClient(target_cfg, target_cfg.get_password(name))
        self._clients[name] = client
        return client

    def disconnect(self, target_name: str) -> None:
        if target_name in self._clients:
            self._clients[target_name].close()
            del self._clients[target_name]

    def disconnect_all(self) -> None:
        for name in list(self._clients):
            self.disconnect(name)

    def list_targets(self) -> list[str]:
        return list(self._config.targets.keys())
