"""Pre-flight diagnostics for vmware-log-insight."""

from __future__ import annotations

import logging
import socket
import stat
from pathlib import Path

from rich.console import Console
from rich.table import Table

_log = logging.getLogger("vmware-log-insight.doctor")
console = Console()


def _config_read_only() -> bool | None:
    """Best-effort read of ``read_only`` from the config file.

    Mirrors the ``config_flag`` that ``mcp_server.server`` hands
    :func:`vmware_policy.readonly.apply_read_only_gate`. It must stay identical:
    a doctor that resolves the flag differently from the gate reports a state the
    server does not have. Deliberately uses the default config path, because that
    is the one the gate reads — ``run_doctor(config_path=...)`` inspects some
    other file, not the deployment.
    """
    from vmware_log_insight.config import load_config

    try:
        return load_config().read_only
    except Exception:  # noqa: BLE001 — absent/unreadable config is not an error here
        return None


def _check_read_only() -> tuple[bool, str]:
    """Report the resolved read-only state and where it came from.

    Never fails — read-only being on is a posture, not a fault. It is here
    because an operator who set the switch had no way to confirm it took: the
    only signal was a line in the MCP server's start-up log.
    """
    from vmware_policy.readonly import read_only_status

    status = read_only_status("vmware-log-insight", _config_read_only())
    if not status.recognised:
        return True, (
            f"{status.source}={status.raw!r} is not a recognised value. It resolves "
            f"to ON (fail-closed), so any write tool would be withheld — probably "
            f"not what was intended. Use true or false."
        )
    if status.enabled:
        return True, (
            f"ON (from {status.source}) — no write tools exist here; the gate "
            f"verifies that at start-up."
        )
    return True, f"off (from {status.source}) — this skill is read-only either way"


def run_doctor(config_path: Path | None = None, skip_auth: bool = False) -> bool:
    """Run all pre-flight checks. Returns True if all pass."""
    from vmware_log_insight.config import CONFIG_FILE, ENV_FILE, load_config

    checks: list[tuple[str, bool, str]] = []

    # 1. Config file exists
    path = config_path or CONFIG_FILE
    if path.exists():
        checks.append(("Config file", True, str(path)))
    else:
        checks.append(
            ("Config file", False, f"Not found: {path}. Copy config.example.yaml to {CONFIG_FILE}")
        )

    # 2. .env permissions
    if ENV_FILE.exists():
        try:
            perms = stat.S_IMODE(ENV_FILE.stat().st_mode)
            if perms & (stat.S_IRWXG | stat.S_IRWXO):
                checks.append((".env permissions", False, f"{oct(perms)} too open. Run: chmod 600 {ENV_FILE}"))
            else:
                checks.append((".env permissions", True, f"{oct(perms)} (owner-only)"))
        except OSError as e:
            checks.append((".env permissions", False, str(e)))
    else:
        checks.append((".env permissions", True, "No .env file (using shell env vars)"))

    # 3. Parse config
    config = None
    try:
        config = load_config(path)
        checks.append(("Config parse", True, f"{len(config.targets)} target(s) configured"))
    except Exception as e:
        checks.append(("Config parse", False, str(e)))

    # 3b. Read-only mode — a state report, not a pass/fail gate. Placed before the
    # early return below because the switch is resolved from the environment and
    # holds whether or not a config file parses: an operator debugging a broken
    # config still needs to know the deployment is locked down.
    passed, detail = _check_read_only()
    checks.append(("Read-only mode", passed, detail))

    if config is None:
        _print_table(checks)
        return False

    # 4. Password env vars set
    for name, target_cfg in config.targets.items():
        try:
            target_cfg.get_password(name)
            checks.append((f"Password ({name})", True, "Set"))
        except OSError as e:
            checks.append((f"Password ({name})", False, str(e)))

    # 5. Network connectivity (TCP to the API port)
    for name, target_cfg in config.targets.items():
        try:
            socket.create_connection((target_cfg.host, target_cfg.port), timeout=5).close()
            checks.append((f"Network ({name})", True, f"{target_cfg.host}:{target_cfg.port} reachable"))
        except OSError as e:
            checks.append((f"Network ({name})", False, f"Cannot reach {target_cfg.host}:{target_cfg.port} - {e}"))

    # 6 & 7. Authentication + appliance version
    if not skip_auth:
        for name, target_cfg in config.targets.items():
            try:
                from vmware_log_insight.connection import ConnectionManager

                mgr = ConnectionManager(config)
                client = mgr.connect(name)
                checks.append((f"Auth ({name})", True, "Session acquired"))
                try:
                    from vmware_log_insight.ops.fields import get_version

                    ver = get_version(client)
                    checks.append((f"Version ({name})", True, ver.get("version") or "unknown"))
                except Exception as e:
                    checks.append((f"Version ({name})", False, str(e)))
                mgr.disconnect(name)
            except Exception as e:
                checks.append((f"Auth ({name})", False, str(e)))

    # 8. MCP server import
    try:
        import mcp_server.server  # noqa: F401

        checks.append(("MCP server import", True, "mcp_server.server importable"))
    except Exception as e:
        checks.append(("MCP server import", False, str(e)))

    _print_table(checks)
    return all(passed for _, passed, _ in checks)


def _print_table(checks: list[tuple[str, bool, str]]) -> None:
    table = Table(title="vmware-log-insight Doctor", show_header=True)
    table.add_column("Check", style="bold")
    table.add_column("Status")
    table.add_column("Detail")
    for name, passed, detail in checks:
        status = "[green]PASS[/green]" if passed else "[red]FAIL[/red]"
        table.add_row(name, status, detail)
    console.print(table)
