"""Regression evals for vmware-log-insight. Failures block release.

Covers 踩坑 #34 (every advertised tool is actually exposed over MCP + schemas
build, #33), the read-only invariant, and the presence of the .env obfuscation
helpers (the whole reason this skill ships the b64 pattern from day one).
"""
from __future__ import annotations

import asyncio

from vmware_log_insight.mcp_server.server import mcp
from vmware_log_insight import config

_EXPECTED_TOOLS = {
    "log_search", "log_aggregate", "log_fields", "log_version",
    "alert_list", "alert_get", "alert_history",
}


def test_mcp_exposes_exactly_the_expected_tools():
    """踩坑 #34: CLI/advertised tool count must equal the MCP-exposed set, and
    #33: FastMCP must build every schema without raising."""
    names = {t.name for t in asyncio.run(mcp.list_tools())}
    assert names == _EXPECTED_TOOLS


def test_all_tools_are_read_only():
    """This skill is non-destructive by construction — no tool may be a write."""
    for t in asyncio.run(mcp.list_tools()):
        ann = t.annotations
        # annotations may be a pydantic model or None; coerce to dict.
        data = ann.model_dump() if hasattr(ann, "model_dump") else (ann or {})
        assert data.get("readOnlyHint") is True, f"{t.name} is not marked read-only"
        assert data.get("destructiveHint") is False, f"{t.name} marked destructive"


def test_config_has_env_obfuscation_helpers():
    """The .env b64 obfuscation must be built in (per the family decision)."""
    assert hasattr(config, "_autoencode_env_file")
    assert hasattr(config, "_decode_secret")
    assert hasattr(config, "_is_b64_token")
