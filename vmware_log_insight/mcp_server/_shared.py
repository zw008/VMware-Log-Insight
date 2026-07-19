"""Shared MCP plumbing for the vmware-log-insight tool modules.

Tool functions live in ``vmware_log_insight/mcp_server/tools/*.py`` and register onto the
single
``mcp`` instance defined here. This module imports nothing from the tool
packages (tools import *from* ``_shared``, never the reverse) to avoid a circular
import. ``vmware_log_insight/mcp_server/server.py`` re-exports these so the historical
import paths
keep resolving.
"""

import logging
import os
from pathlib import Path
from typing import Any, Optional

from mcp.server.fastmcp import FastMCP
from vmware_policy import sanitize

from vmware_log_insight.config import load_config
from vmware_log_insight.connection import ConnectionManager, LogInsightApiError

logger = logging.getLogger("mcp_server")


def _safe_error(exc: Exception, tool: str) -> str:
    """Return an agent-safe error string; log full detail server-side only.

    LogInsightApiError (the connection layer's teaching errors) and intentional
    validation errors pass through; anything else is masked so raw response
    bodies / host:port pairs never reach the agent.
    """
    logger.error("Tool %s failed", tool, exc_info=True)
    if isinstance(
        exc,
        (LogInsightApiError, ValueError, FileNotFoundError, KeyError, PermissionError, ConnectionError),
    ):
        return sanitize(str(exc), 300)
    return f"{type(exc).__name__}: operation failed."


mcp = FastMCP(
    "vmware-log-insight",
    instructions=(
        "VMware Aria Operations for Logs (vRealize Log Insight): read-only log "
        "search, aggregation/spike detection, field discovery, and alert queries. "
        "Feed results to vmware-debug's incident_timeline to correlate with events "
        "from other sources. For vCenter events/alarms use vmware-monitor; for "
        "metrics/anomalies use vmware-aria."
    ),
)

_conn_mgr: Optional[ConnectionManager] = None


def _get_connection(target: Optional[str] = None) -> Any:
    """Return a LogInsightClient, lazily initialising the connection manager."""
    global _conn_mgr  # noqa: PLW0603
    if _conn_mgr is None:
        config_path_str = os.environ.get("VMWARE_LOG_INSIGHT_CONFIG")
        config_path = Path(config_path_str) if config_path_str else None
        _conn_mgr = ConnectionManager(load_config(config_path))
    return _conn_mgr.connect(target)
