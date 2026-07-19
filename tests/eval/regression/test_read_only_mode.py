"""Read-only mode must be a no-op here — and that is worth pinning.

Regression source: VMware-AIops issue #31 (juanpf-ha). An operator driving the
family with a local Llama 3.3 70B had to hand-write the prompt instruction
"work exclusively in read-only mode and never modify alerts, definitions,
reports or configuration", because read-only was only ever a documented
intent. A weak model can ignore a prompt; it cannot call a tool that is not in
list_tools().

vmware-log-insight is read-only by design: all 7 tools query logs and alerts,
none mutates anything. So the interesting assertion is the *inverse* of the
one Aria makes — turning read-only mode on must withhold nothing and leave the
server fully functional. If a future write tool lands here without a [WRITE]
marker, ``test_every_tool_is_marked_read`` goes red; if it lands *with* one,
``test_read_only_withholds_nothing`` goes red. Either way the change is
visible rather than silent.
"""

import asyncio
import importlib
import sys

import pytest
from vmware_policy import apply_read_only_gate

EXPECTED_TOOLS = {
    "log_search",
    "log_aggregate",
    "log_fields",
    "log_version",
    "alert_list",
    "alert_get",
    "alert_history",
}


def _load_server(monkeypatch, read_only):
    """Import vmware_log_insight.mcp_server.server fresh under the given read-only env."""
    monkeypatch.delenv("VMWARE_READ_ONLY", raising=False)
    monkeypatch.delenv("VMWARE_LOG_INSIGHT_READ_ONLY", raising=False)
    if read_only is not None:
        monkeypatch.setenv("VMWARE_READ_ONLY", read_only)

    for name in [m for m in sys.modules if m.startswith("vmware_log_insight.mcp_server")]:
        del sys.modules[name]
    return importlib.import_module("vmware_log_insight.mcp_server.server")


def _tools(server):
    return asyncio.run(server.mcp.list_tools())


def _tool_names(server):
    return {t.name for t in _tools(server)}


def _write_tools(server):
    """Derive the write set from the live [READ]/[WRITE] docstring markers."""
    names = set()
    for tool in _tools(server):
        description = (tool.description or "").lstrip()
        if description.startswith("[WRITE]"):
            names.add(tool.name)
        elif not description.startswith("[READ]"):  # pragma: no cover
            pytest.fail(f"tool {tool.name} has no [READ]/[WRITE] marker")
    return names


@pytest.fixture(autouse=True)
def _restore_modules():
    """Put back the exact module objects other test files already hold.

    Deleting them is not enough: the tool modules bind helpers from
    ``vmware_log_insight.mcp_server._shared`` at import time, and sibling tests monkeypatch those
    on the module objects they imported at collection time.
    """
    saved = {n: m for n, m in sys.modules.items() if n.startswith("vmware_log_insight.mcp_server")}
    yield
    for name in [m for m in sys.modules if m.startswith("vmware_log_insight.mcp_server")]:
        del sys.modules[name]
    sys.modules.update(saved)


def test_no_tool_is_marked_write(monkeypatch):
    """The premise: this skill has no write tools to withhold."""
    server = _load_server(monkeypatch, None)
    assert _write_tools(server) == set()


def test_default_mode_exposes_every_tool(monkeypatch):
    server = _load_server(monkeypatch, None)
    assert _tool_names(server) == EXPECTED_TOOLS
    assert server.WITHHELD_WRITE_TOOLS == []


def test_read_only_withholds_nothing(monkeypatch):
    """Read-only mode must not cost this skill any capability."""
    server = _load_server(monkeypatch, "true")
    assert server.WITHHELD_WRITE_TOOLS == []


def test_read_only_keeps_every_tool(monkeypatch):
    """Every tool survives — the whole point of testing a read-only skill."""
    server = _load_server(monkeypatch, "true")
    assert _tool_names(server) == EXPECTED_TOOLS


def test_skill_env_var_also_withholds_nothing(monkeypatch):
    monkeypatch.delenv("VMWARE_READ_ONLY", raising=False)
    monkeypatch.setenv("VMWARE_LOG_INSIGHT_READ_ONLY", "true")
    for name in [m for m in sys.modules if m.startswith("vmware_log_insight.mcp_server")]:
        del sys.modules[name]
    server = importlib.import_module("vmware_log_insight.mcp_server.server")
    assert server.WITHHELD_WRITE_TOOLS == []
    assert _tool_names(server) == EXPECTED_TOOLS


def test_every_tool_is_marked_read(monkeypatch):
    """The [READ] marker is what the gate classifies on — keep it accurate."""
    server = _load_server(monkeypatch, "true")
    for tool in _tools(server):
        assert (tool.description or "").lstrip().startswith("[READ]"), tool.name


def test_gate_is_live_not_a_no_op(monkeypatch):
    """An empty withheld list must mean "no write tools", not "gate never ran".

    Every other assertion in this file is satisfied just as well by a gate that
    was never wired in. Register a tool this skill does not have, marked
    [WRITE], and prove the gate removes it under the same env and skill name
    the module-level call uses.
    """
    server = _load_server(monkeypatch, "true")
    assert server.WITHHELD_WRITE_TOOLS == []

    @server.mcp.tool(name="_probe_write")
    def _probe() -> str:
        """[WRITE] Probe tool — must not survive the gate."""
        return "probe"

    assert apply_read_only_gate(server.mcp, "vmware-log-insight") == ["_probe_write"]
    assert _tool_names(server) == EXPECTED_TOOLS


def test_config_flag_is_readable(monkeypatch):
    """_config_read_only must degrade to None when no config file exists."""
    server = _load_server(monkeypatch, None)
    monkeypatch.setenv("VMWARE_LOG_INSIGHT_CONFIG", "/nonexistent/config.yaml")
    assert server._config_read_only() is None


def test_fastmcp_registry_api_still_present(monkeypatch):
    """The gate reaches into _tool_manager.list_tools(); pin that it exists.

    If an mcp upgrade moves this, we want a red test here rather than a gate
    that silently stops removing anything.
    """
    server = _load_server(monkeypatch, None)
    assert callable(getattr(server.mcp, "remove_tool", None))
    assert callable(getattr(server.mcp._tool_manager, "list_tools", None))
    assert server.mcp._tool_manager.list_tools()
