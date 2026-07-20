"""LOG tools (4, read-only): log_search, log_aggregate, log_fields, log_version.

Each resolves the connection/error helpers through ``vmware_log_insight.mcp_server.server``
at call
time, so patching ``server._get_connection`` governs every tool.
"""

from typing import Optional

from vmware_policy import vmware_tool

from vmware_log_insight.mcp_server._shared import mcp

_READ = {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True}


@mcp.tool(annotations=_READ)
@vmware_tool(risk_level="low")
def log_search(
    text: Optional[str] = None,
    last: Optional[str] = None,
    begin_ms: Optional[int] = None,
    end_ms: Optional[int] = None,
    limit: int = 50,
    target: Optional[str] = None,
) -> dict:
    """[READ] Search Log Insight events within a time window.

    WHEN: to find the actual log lines behind an incident (e.g. what vmkernel
    logged during a storage event). For "where did logs burst?" use
    log_aggregate instead; for vCenter alarms use vmware-monitor.

    INPUT: text = free-text search (CONTAINS). last = relative window like "1h",
    "30m", "7d" (defaults to last hour). begin_ms/end_ms = absolute epoch-ms
    window (mutually exclusive with last). limit = max events
    (1..20000, default 50 — narrow with text, don't raise it). target =
    target name from config.

    RETURNS: {count, complete (False if truncated), constraints,
    events: [{timestamp_ms, text, fields}]}. Feed events to vmware-debug
    incident_timeline to correlate across sources. Read-only."""
    from vmware_log_insight.mcp_server import server

    try:
        from vmware_log_insight.ops.search import search_events

        return search_events(
            server._get_connection(target),
            text=text, last=last, begin_ms=begin_ms, end_ms=end_ms, limit=limit,
        )
    except Exception as e:
        return {"error": server._safe_error(e, "log_search"), "hint": "Run 'vmware-log-insight doctor'."}


@mcp.tool(annotations=_READ)
@vmware_tool(risk_level="low")
def log_aggregate(
    text: Optional[str] = None,
    last: Optional[str] = None,
    begin_ms: Optional[int] = None,
    end_ms: Optional[int] = None,
    aggregation: str = "COUNT",
    bin_width_ms: int = 60000,
    target: Optional[str] = None,
) -> dict:
    """[READ] Aggregate matching events into a time series and detect spikes.

    WHEN: to find when/whether log volume burst without pulling raw events. Follow up with log_search on the spike window.

    INPUT: text/last/begin_ms/end_ms = same query semantics as log_search.
    aggregation = COUNT|UCOUNT|AVG|MIN|MAX|SUM|STDDEV|VARIANCE|SAMPLE (default
    COUNT). bin_width_ms = bin width in ms (default 60000). target = target
    name from config.

    RETURNS: {aggregation, bin_width_ms, constraints, bins:[{timestamp_ms,
    value}], spikes:[{timestamp_ms, value, zscore}]}. Read-only."""
    from vmware_log_insight.mcp_server import server

    try:
        from vmware_log_insight.ops.aggregate import aggregate_events

        return aggregate_events(
            server._get_connection(target),
            text=text, last=last, begin_ms=begin_ms, end_ms=end_ms,
            aggregation=aggregation, bin_width_ms=bin_width_ms,
        )
    except Exception as e:
        return {"error": server._safe_error(e, "log_aggregate"), "hint": "Run 'vmware-log-insight doctor'."}


@mcp.tool(annotations=_READ)
@vmware_tool(risk_level="low")
def log_fields(name_filter: Optional[str] = None, target: Optional[str] = None) -> dict:
    """[READ] List the extracted fields available to use in query filters.

    Use this to discover valid field names before filtering log_search /
    log_aggregate. name_filter = optional case-insensitive substring. target =
    target name from config. Returns the family list envelope {items, returned,
    limit, total, truncated, hint}; each item is {name}. No limit — every
    matching field is returned, so truncated is always false: this is the
    complete field list, not a page. Read-only."""
    from vmware_log_insight.mcp_server import server

    try:
        from vmware_log_insight.ops.fields import list_fields

        return list_fields(server._get_connection(target), name_filter=name_filter)
    except Exception as e:
        return {"error": server._safe_error(e, "log_fields"), "hint": "Run 'vmware-log-insight doctor'."}


@mcp.tool(annotations=_READ)
@vmware_tool(risk_level="low")
def log_version(target: Optional[str] = None) -> dict:
    """[READ] Return the Log Insight appliance version/build (diagnostics and
    query-syntax compatibility). target = target name from config. Use this
    first when a query behaves unexpectedly, to confirm the appliance
    version before trusting log_search. Read-only."""
    from vmware_log_insight.mcp_server import server

    try:
        from vmware_log_insight.ops.fields import get_version

        return get_version(server._get_connection(target))
    except Exception as e:
        return {"error": server._safe_error(e, "log_version"), "hint": "Run 'vmware-log-insight doctor'."}
