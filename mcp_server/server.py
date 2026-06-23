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

__all__ = [
    "mcp",
    "main",
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
