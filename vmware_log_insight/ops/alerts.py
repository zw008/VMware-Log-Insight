"""Alert queries: GET /api/v2/alerts, /alerts/{id}, /alerts/{id}/history.

Read-only — this skill never creates, edits, or deletes alerts. All text is
sanitized.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from vmware_policy import sanitize

if TYPE_CHECKING:
    from vmware_log_insight.connection import LogInsightClient

_DEFAULT_LIMIT = 50


def _summarize_alert(a: dict) -> dict:
    """Project one alert onto high-signal summary fields."""
    return {
        "id": sanitize(str(a.get("id", a.get("alertId", ""))), 100),
        "name": sanitize(str(a.get("name", "")), 200),
        "enabled": a.get("enabled"),
        "info": sanitize(str(a.get("info", a.get("description", ""))), 500),
    }


def list_alerts(
    client: LogInsightClient,
    name_filter: str | None = None,
    limit: int = _DEFAULT_LIMIT,
) -> list[dict]:
    """List defined alerts.

    Args:
        client: Authenticated Log Insight client.
        name_filter: Optional case-insensitive substring filter on alert name.
        limit: Max alerts to return. Default 50.

    Returns:
        List of {id, name, enabled, info}. Pass an id to get_alert for details.
    """
    data = client.get("/alerts")
    items = data.get("alerts", []) or []
    filt = name_filter.lower() if name_filter else None
    out: list[dict] = []
    for a in items:
        summary = _summarize_alert(a)
        if filt and filt not in summary["name"].lower():
            continue
        out.append(summary)
        if len(out) >= limit:
            break
    return out


def get_alert(client: LogInsightClient, alert_id: str) -> dict:
    """Get full details for one alert by id.

    Args:
        client: Authenticated Log Insight client.
        alert_id: The alert id (from list_alerts).

    Returns:
        The alert's full (sanitized) detail dict.
    """
    if not alert_id:
        raise ValueError("alert_id must not be empty")
    data = client.get(f"/alerts/{alert_id}")
    summary = _summarize_alert(data)
    summary["raw_keys"] = sorted(k for k in data if isinstance(k, str))
    return summary


def get_alert_history(
    client: LogInsightClient, alert_id: str, limit: int = _DEFAULT_LIMIT
) -> list[dict]:
    """List recent trigger-history records for an alert.

    Args:
        client: Authenticated Log Insight client.
        alert_id: The alert id (from list_alerts).
        limit: Max history records to return. Default 50.

    Returns:
        List of {timestamp_ms, info} records, most recent first as returned.
    """
    if not alert_id:
        raise ValueError("alert_id must not be empty")
    data = client.get(f"/alerts/{alert_id}/history")
    records = data.get("history", data.get("records", [])) or []
    out: list[dict] = []
    for r in records[:limit]:
        out.append(
            {
                "timestamp_ms": r.get("timestamp", r.get("time")),
                "info": sanitize(str(r.get("info", r.get("message", ""))), 500),
            }
        )
    return out
