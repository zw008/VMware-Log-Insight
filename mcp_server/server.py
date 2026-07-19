"""MCP server for VMware Log Insight (Aria Operations for Logs) — read-only.

Thin entrypoint: importing the tool modules runs their ``@mcp.tool`` decorators
(registering the 7 read tools on the shared ``mcp`` instance), re-exports the
shared plumbing and every tool function so ``from mcp_server.server import mcp,
<fn>`` keeps resolving (踩坑 #17), and exposes ``main()``.

Tool categories
---------------
* **Logs** (4, read-only): log_search, log_aggregate, log_fields, log_version
  — ``mcp_server/tools/logs.py``
* **Alerts** (3, read-only): alert_list, alert_get, alert_history
  — ``mcp_server/tools/alerts.py``

Security: stdio transport (local only, no listener); credentials come from
env/.env, never MCP messages; all API text passes through sanitize().
For vCenter events/alarms use vmware-monitor; for metrics use vmware-aria.
"""

import logging
import sys
from typing import Optional

from vmware_policy import apply_read_only_gate, mtime_cached_loader, set_environment_resolver

from vmware_log_insight.config import CONFIG_FILE, load_config

# Shared plumbing — re-exported so `from mcp_server.server import _safe_error,
# mcp, _get_connection` (and monkeypatch targets) keep resolving.
from mcp_server._shared import (  # noqa: F401
    _get_connection,
    _safe_error,
    logger,
    mcp,
)

# Importing the tool modules runs their @mcp.tool decorators (registration).
from mcp_server.tools import (  # noqa: F401
    alerts,
    logs,
)

# Re-export every tool function so `mcp_server.server.<tool>` resolves (tests
# call e.g. `server.log_search(...)` and patch `server._get_connection`).
from mcp_server.tools.alerts import (  # noqa: F401
    alert_get,
    alert_history,
    alert_list,
)
from mcp_server.tools.logs import (  # noqa: F401
    log_aggregate,
    log_fields,
    log_search,
    log_version,
)

# ---------------------------------------------------------------------------
# Read-only gate
# ---------------------------------------------------------------------------


def _config_read_only() -> Optional[bool]:
    """Best-effort read of ``read_only`` from the config file.

    Runs at import time, when no config file need exist yet (tests, ``--help``,
    smoke checks), so every failure degrades to "not configured" and lets the
    env vars decide. None and False are equivalent here — config is the last
    link in the precedence chain — but None keeps 'not configured'
    distinguishable from 'configured off' in logs and debugging.
    """
    try:
        return load_config().read_only
    except Exception:  # noqa: BLE001 — absent/unreadable config is not an error here
        return None


# Applied once, after every tool module above has registered. All 7 tools are
# read-only, so nothing is withheld — the empty list is the assertion that this
# skill really is non-destructive, checked by tests/eval/regression.
WITHHELD_WRITE_TOOLS: list[str] = apply_read_only_gate(
    mcp, "vmware-log-insight", config_flag=_config_read_only()
)


# ---------------------------------------------------------------------------
# Environment declaration
# ---------------------------------------------------------------------------


_cached_config = mtime_cached_loader("VMWARE_LOG_INSIGHT_CONFIG", CONFIG_FILE, load_config)


def _environment_for(target: Optional[str]) -> str:
    """Report the environment a target declares, for policy scoping.

    Policy rules scope by environment ("irreversible work in production needs a
    second person"), and vmware-policy cannot read this skill's config itself.
    Registering this lookup is what lets those rules fire at all. Reloaded on
    config.yaml mtime change so an edit takes effect without restarting the
    server. The config is cached via :func:`vmware_policy.mtime_cached_loader`,
    so repeated tool calls pay one ``os.stat`` instead of a full YAML parse.

    Every tool this skill ships is read-only, and reads are never gated by the
    declaration rule — so nothing here is gated *today*. It is registered so
    that the first write tool added is scoped correctly on the day it lands,
    rather than shipping unprotected because the wiring was never done.
    """
    try:
        return _cached_config().environment_for(target)
    except Exception:  # noqa: BLE001 — an unreadable config means "undeclared"
        return ""


set_environment_resolver(_environment_for)

__all__ = [
    "mcp",
    "main",
    "WITHHELD_WRITE_TOOLS",
    "_environment_for",
    "_safe_error",
    "_get_connection",
    "log_search",
    "log_aggregate",
    "log_fields",
    "log_version",
    "alert_list",
    "alert_get",
    "alert_history",
]


def main() -> None:
    """Start the MCP server using stdio transport.

    Guards Python < 3.11: FastMCP schema reflection over tool signatures is
    unreliable on 3.10 with older mcp/pydantic (踩坑 #33).
    """
    if sys.version_info < (3, 11):
        sys.exit(
            "vmware-log-insight MCP server requires Python >= 3.11. Reinstall: "
            "uv tool install --python 3.11 --force vmware-log-insight"
        )
    logging.basicConfig(
        level=logging.WARNING,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    mcp.run()


if __name__ == "__main__":
    main()
