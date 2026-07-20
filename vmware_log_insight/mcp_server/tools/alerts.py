"""ALERT tools (3, read-only): alert_list, alert_get, alert_history."""

from typing import Optional

from vmware_policy import vmware_tool

from vmware_log_insight.mcp_server._shared import mcp

_READ = {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True}


@mcp.tool(annotations=_READ)
@vmware_tool(risk_level="low")
def alert_list(
    name_filter: Optional[str] = None, limit: int = 50, target: Optional[str] = None
) -> dict:
    """[READ] List defined Log Insight alerts.

    name_filter = optional case-insensitive substring on alert name. limit = max
    results (default 50). target = target name from config. Returns the family
    list envelope {items, returned, limit, total, truncated, hint}; each item is
    {id, name, enabled, info}. Start here, then pass an id to alert_get or
    alert_history. total is the real count matching name_filter, so truncated
    answers whether more exist; raise limit or narrow name_filter when true. Read-only — this skill never
    creates/edits/deletes alerts."""
    from vmware_log_insight.mcp_server import server

    try:
        from vmware_log_insight.ops.alerts import list_alerts

        return list_alerts(server._get_connection(target), name_filter=name_filter, limit=limit)
    except Exception as e:
        return {"error": server._safe_error(e, "alert_list"), "hint": "Run 'vmware-log-insight doctor'."}


@mcp.tool(annotations=_READ)
@vmware_tool(risk_level="low")
def alert_get(alert_id: str, target: Optional[str] = None) -> dict:
    """[READ] Get full details for one alert. Use this after alert_list;
    alert_id = the id it returned. target = target name from config. Returns
    the alert's sanitized detail; for its firings use alert_history.
    Read-only."""
    from vmware_log_insight.mcp_server import server

    try:
        from vmware_log_insight.ops.alerts import get_alert

        return get_alert(server._get_connection(target), alert_id)
    except Exception as e:
        return {"error": server._safe_error(e, "alert_get"), "hint": "Run 'vmware-log-insight doctor'."}


@mcp.tool(annotations=_READ)
@vmware_tool(risk_level="low")
def alert_history(alert_id: str, limit: int = 50, target: Optional[str] = None) -> dict:
    """[READ] List recent trigger-history records for an alert.

    Use this for when an alert fired, not how it's defined.
    alert_id = the alert id (from alert_list). limit = max records (default 50).
    target = target name from config. Returns the family list envelope {items,
    returned, limit, total, truncated, hint}; each item is {timestamp_ms, info}.
    total is the real history-record count, so truncated answers whether older
    records were left behind — raise limit when true. Read-only."""
    from vmware_log_insight.mcp_server import server

    try:
        from vmware_log_insight.ops.alerts import get_alert_history

        return get_alert_history(server._get_connection(target), alert_id, limit=limit)
    except Exception as e:
        return {"error": server._safe_error(e, "alert_history"), "hint": "Run 'vmware-log-insight doctor'."}
