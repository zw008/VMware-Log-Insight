"""Event search: GET /api/v2/events/{constraints}.

Returns high-signal event summaries (timestamp + text + a flattened fields dict),
default-paginated, with the query text passed back so the caller can refine.
All API text passes through sanitize() (prompt-injection defence).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from vmware_policy import sanitize

from vmware_log_insight.constraints import build_constraints

if TYPE_CHECKING:
    from vmware_log_insight.connection import LogInsightClient

_log = logging.getLogger("vmware-log-insight.ops.search")

# Family rule: search over list. Default page size kept small and high-signal;
# the server hard-caps at 20000.
_DEFAULT_LIMIT = 50
_MAX_LIMIT = 20000


def _flatten_fields(event: dict) -> dict[str, str]:
    """Flatten Log Insight's ``fields: [{name, content}]`` into a dict.

    Defensive: the wire shape is a list of {name, content}; some renderings use
    a plain dict. Both are handled, and values are sanitized.
    """
    raw = event.get("fields")
    out: dict[str, str] = {}
    if isinstance(raw, list):
        for f in raw:
            name = f.get("name")
            if name:
                out[sanitize(str(name), 200)] = sanitize(str(f.get("content", "")), 500)
    elif isinstance(raw, dict):
        for name, content in raw.items():
            out[sanitize(str(name), 200)] = sanitize(str(content), 500)
    return out


def _summarize_event(event: dict) -> dict:
    """Project one raw event onto the high-signal summary we return."""
    return {
        "timestamp_ms": event.get("timestamp"),
        "text": sanitize(str(event.get("text", "")), 1000),
        "fields": _flatten_fields(event),
    }


def search_events(
    client: LogInsightClient,
    *,
    text: str | None = None,
    last: str | int | None = None,
    begin_ms: int | None = None,
    end_ms: int | None = None,
    filters: list[tuple[str, str, str]] | None = None,
    limit: int = _DEFAULT_LIMIT,
) -> dict:
    """Search log events within a time window.

    Args:
        client: Authenticated Log Insight client.
        text: Free-text search (matched with CONTAINS).
        last: Relative window ("1h", "30m", int seconds). Default last hour if no
            window is given. Mutually exclusive with begin_ms/end_ms.
        begin_ms / end_ms: Absolute epoch-ms window.
        filters: Extra (field, operator, value) constraints.
        limit: Max events to return (1..20000). Default 50 — narrow with text /
            filters rather than raising this.

    Returns:
        {"count", "complete" (bool, False if the server truncated), "constraints"
        (the query string used), "events": [{timestamp_ms, text, fields}]}.
    """
    limit = max(1, min(limit, _MAX_LIMIT))
    constraints = build_constraints(
        text=text, last=last, begin_ms=begin_ms, end_ms=end_ms, filters=filters
    )
    data = client.get(f"/events/{constraints}", params={"limit": limit})

    events = [_summarize_event(e) for e in data.get("events", []) or []]
    return {
        "count": len(events),
        # `complete=False` means the server returned a partial result set.
        "complete": data.get("complete", True),
        "constraints": constraints,
        "events": events,
    }
