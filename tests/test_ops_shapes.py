"""Ops response-shaping tests using a fake client (no live appliance).

Pins the high-signal summary shapes and the defensive parsing of the documented
wire variants. Exact wire schemas need real-instance confirmation (BACKLOG), so
these assert our normalization of the *documented* shapes, not the live server.
"""

from __future__ import annotations

from vmware_log_insight.ops.aggregate import aggregate_events, detect_spikes
from vmware_log_insight.ops.alerts import get_alert_history, list_alerts
from vmware_log_insight.ops.fields import list_fields
from vmware_log_insight.ops.search import search_events


class FakeClient:
    """Records the last GET path and returns a canned payload."""

    def __init__(self, payload: dict):
        self.payload = payload
        self.last_path = None
        self.last_params = None

    def get(self, path, params=None, **kwargs):
        self.last_path = path
        self.last_params = params
        return self.payload


def test_search_flattens_fields_list():
    client = FakeClient(
        {
            "complete": True,
            "events": [
                {
                    "timestamp": 1000,
                    "text": "scsi apd on naa.600",
                    "fields": [{"name": "hostname", "content": "esxi-03"}],
                }
            ],
        }
    )
    out = search_events(client, text="apd", last="1h", limit=10)
    assert out["count"] == 1
    ev = out["events"][0]
    assert ev["timestamp_ms"] == 1000
    assert ev["fields"] == {"hostname": "esxi-03"}
    # constraints string + limit param were built and passed through
    assert client.last_path.startswith("/events/")
    assert client.last_params == {"limit": 10}


def test_search_handles_dict_fields_variant():
    client = FakeClient({"events": [{"timestamp": 1, "text": "x", "fields": {"k": "v"}}]})
    out = search_events(client, last="1h")
    assert out["events"][0]["fields"] == {"k": "v"}


def test_aggregate_normalizes_bins_and_detects_spike():
    bins = [{"timestamp": i, "value": 1} for i in range(9)]
    bins.append({"timestamp": 9, "value": 50})
    client = FakeClient({"bins": bins})
    out = aggregate_events(client, last="1h", aggregation="count")
    assert out["aggregation"] == "COUNT"
    assert len(out["bins"]) == 10
    assert out["spikes"] and out["spikes"][-1]["value"] == 50


def test_aggregate_rejects_unknown_function():
    import pytest

    with pytest.raises(ValueError):
        aggregate_events(FakeClient({}), aggregation="MEDIAN")


def test_detect_spikes_needs_baseline():
    assert detect_spikes([{"value": 1}, {"value": 99}]) == []


def test_list_fields_filters():
    client = FakeClient({"fields": [{"name": "hostname"}, {"name": "appname"}]})
    out = list_fields(client, name_filter="host")
    assert out == [{"name": "hostname"}]


def test_list_alerts_summary_and_limit():
    client = FakeClient(
        {"alerts": [{"id": "a1", "name": "Disk full", "enabled": True, "info": "x"}]}
    )
    out = list_alerts(client, limit=5)
    assert out[0]["id"] == "a1" and out[0]["enabled"] is True


def test_alert_history_variant_keys():
    client = FakeClient({"records": [{"time": 5, "message": "fired"}]})
    out = get_alert_history(client, "a1")
    assert out == [{"timestamp_ms": 5, "info": "fired"}]
