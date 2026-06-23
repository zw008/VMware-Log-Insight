"""Field + appliance metadata: GET /api/v2/fields and GET /api/v2/version."""

from __future__ import annotations

from typing import TYPE_CHECKING

from vmware_policy import sanitize

if TYPE_CHECKING:
    from vmware_log_insight.connection import LogInsightClient


def list_fields(client: LogInsightClient, name_filter: str | None = None) -> list[dict]:
    """List the extracted fields available for use in query constraints.

    Args:
        client: Authenticated Log Insight client.
        name_filter: Optional case-insensitive substring filter on field name.

    Returns:
        List of {name} dicts. Use these names in search/aggregate ``filters``.
    """
    data = client.get("/fields")
    items = data.get("fields", data.get("fieldName", [])) or []
    filt = name_filter.lower() if name_filter else None
    out: list[dict] = []
    for f in items:
        name = sanitize(str(f.get("name", f) if isinstance(f, dict) else f), 200)
        if filt and filt not in name.lower():
            continue
        out.append({"name": name})
    return out


def get_version(client: LogInsightClient) -> dict:
    """Return the Log Insight appliance version/build info.

    Useful for diagnostics and for confirming query-syntax compatibility.
    """
    data = client.get("/version")
    return {
        "version": sanitize(str(data.get("version", "")), 100),
        "release_name": sanitize(str(data.get("releaseName", "")), 100),
        "build": sanitize(str(data.get("build", data.get("buildNumber", ""))), 100),
    }
