"""A target must declare its environment, and writes are scoped by it.

Policy rules scope by environment ("irreversible work in production needs a
second person"). Environment used to be derived from the *target's name*, so
those rules only fired when an operator happened to name a target the exact
string in the rule — nobody names a target "production", so the control was
configured and inert.

Environment is now an explicit `environment:` declaration in config.yaml. The
rollout is two steps, because the end state refuses operations that work today:

  * the shipped baseline sets ``require_declared_environment: warn`` — an
    undeclared write RUNS and logs a warning naming the fix;
  * the next major release ships ``true`` and REFUSES it.

Both are pinned here so the enforcing release is a one-word change to a path
already under test.

Note this skill ships **no write tools** — all 7 are read-only — so nothing it
exposes is gated under either setting. The gate is still wired, and exercised
here against a locally defined @vmware_tool, so the first write tool added
lands scoped instead of shipping unprotected. The read-side guarantee is the
one that matters right now: an unlabelled target must stay fully inspectable.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from mcp_server import server
from vmware_log_insight.config import AppConfig, TargetConfig
from vmware_policy import vmware_tool
from vmware_policy.decorators import PolicyDenied
from vmware_policy.environment import set_environment_resolver
from vmware_policy.policy import get_policy_engine, reset_policy_engine


def _config(environment: str) -> AppConfig:
    return AppConfig(
        targets={
            "lab": TargetConfig(
                host="10.0.0.50", username="admin", environment=environment
            )
        },
        default_target="lab",
    )


@pytest.fixture()
def declared(request: pytest.FixtureRequest):
    """Run the MCP server's real resolver over a config we control.

    ``request.param`` is what the target declares — "" for an unlabelled target.
    """
    with patch("mcp_server.server._cached_config", return_value=_config(request.param)):
        set_environment_resolver(server._environment_for)
        yield
    set_environment_resolver(None)


@pytest.fixture()
def baseline():
    """The shipped policy baseline — currently the warn-only migration setting."""
    reset_policy_engine()
    get_policy_engine()
    yield
    reset_policy_engine()


@pytest.fixture()
def enforcing(tmp_path):
    """The same rules with the requirement switched on, as the next major
    release will ship it."""
    rules = tmp_path / "rules.yaml"
    rules.write_text("require_declared_environment: true\n")
    reset_policy_engine()
    get_policy_engine(rules)
    yield
    reset_policy_engine()


# A stand-in for the first write tool this skill grows. Defined here rather than
# reaching for a product tool because there is not one yet.
@vmware_tool(risk_level="medium")
def _state_changing_probe(target: str = "") -> str:
    return "ran"


@vmware_tool(risk_level="low")
def _read_only_probe(target: str = "") -> str:
    return "ran"


# ---------------------------------------------------------------------------
# Migration window (shipped today): undeclared writes run, but warn
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("declared", [""], indirect=True)
def test_undeclared_write_runs_and_warns_under_baseline(declared, baseline) -> None:
    """Nothing breaks for operators who have not labelled their estate yet."""
    assert _state_changing_probe(target="lab") == "ran"

    result = get_policy_engine().check_allowed(
        "_state_changing_probe", env="", risk_level="medium"
    )
    assert result.allowed is True
    assert result.rule == "undeclared_environment_warning"
    assert "future release will refuse" in result.reason.lower()


# ---------------------------------------------------------------------------
# Enforcing release: undeclared writes are refused
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("declared", [""], indirect=True)
def test_undeclared_write_is_denied_when_enforcing(declared, enforcing) -> None:
    with pytest.raises(PolicyDenied) as excinfo:
        _state_changing_probe(target="lab")

    assert excinfo.value.result.rule == "undeclared_environment"


@pytest.mark.parametrize("declared", [""], indirect=True)
def test_denial_names_the_config_key(declared, enforcing) -> None:
    """An operator has to be able to act on the refusal without reading code."""
    with pytest.raises(PolicyDenied) as excinfo:
        _state_changing_probe(target="lab")

    reason = str(excinfo.value)
    assert "environment" in reason
    assert "config.yaml" in reason


@pytest.mark.parametrize("declared", ["lab"], indirect=True)
def test_declared_target_allows_writes_when_enforcing(declared, enforcing) -> None:
    """Declaring the environment is all it takes to be unblocked."""
    assert _state_changing_probe(target="lab") == "ran"


# ---------------------------------------------------------------------------
# Reads are never gated, under either setting
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("declared", ["", "lab"], indirect=True)
@pytest.mark.parametrize("mode", ["baseline", "enforcing"])
def test_reads_are_never_gated(declared, mode, request) -> None:
    request.getfixturevalue(mode)
    assert _read_only_probe(target="lab") == "ran"


@pytest.mark.parametrize("declared", ["", "lab"], indirect=True)
@pytest.mark.parametrize("mode", ["baseline", "enforcing"])
def test_product_read_tools_are_never_gated(declared, mode, request) -> None:
    """The tools this skill actually ships must work against any target.

    This is the guarantee that matters today: Log Insight is a read-only skill,
    so an unlabelled estate must remain completely usable.
    """
    request.getfixturevalue(mode)
    with patch.object(server, "_get_connection", return_value=object()), patch(
        "vmware_log_insight.ops.fields.get_version", return_value={"version": "8.14.0"}
    ):
        out = server.log_version(target="lab")

    assert out == {"version": "8.14.0"}


# ---------------------------------------------------------------------------
# Wiring
# ---------------------------------------------------------------------------


def test_resolver_is_registered_at_import() -> None:
    """Dropping set_environment_resolver() would brick every future write.

    Without a resolver every target reads as undeclared. Under today's warn
    setting that is invisible, so a lost registration would only surface when
    the enforcing release lands. Pin the registration itself.
    """
    import importlib

    import vmware_policy.environment as env_mod

    set_environment_resolver(None)
    try:
        importlib.reload(server)
        assert env_mod._resolver is not None
        assert env_mod._resolver is server._environment_for
    finally:
        set_environment_resolver(None)


class TestConfigParsesTheDeclaration:
    def test_environment_is_read_from_yaml(self, tmp_path) -> None:
        from vmware_log_insight.config import load_config

        cfg_file = tmp_path / "config.yaml"
        cfg_file.write_text(
            "targets:\n"
            "  lab:\n"
            "    host: 10.0.0.50\n"
            "    environment: lab\n"
            "  prod:\n"
            "    host: loginsight.example.com\n"
            "default_target: lab\n"
        )
        cfg = load_config(cfg_file)

        assert cfg.environment_for("lab") == "lab"
        # Declaring nothing must read as undeclared, not as a default.
        assert cfg.environment_for("prod") == ""
        # An omitted target resolves via default_target, so policy and the
        # connection layer never disagree about which host is in play.
        assert cfg.environment_for(None) == "lab"
        # An unknown name is undeclared rather than an exception escaping into
        # a tool call.
        assert cfg.environment_for("nope") == ""

    def test_whitespace_only_declaration_is_undeclared(self, tmp_path) -> None:
        from vmware_log_insight.config import load_config

        cfg_file = tmp_path / "config.yaml"
        cfg_file.write_text(
            "targets:\n"
            "  lab:\n"
            "    host: 10.0.0.50\n"
            "    environment: '   '\n"
            "default_target: lab\n"
        )
        assert load_config(cfg_file).environment_for("lab") == ""

    def test_unreadable_config_reads_as_undeclared(self) -> None:
        """A broken config must fail closed, not raise into the tool call."""
        with patch.object(
            server, "load_config", side_effect=FileNotFoundError("no config")
        ):
            assert server._environment_for("lab") == ""
