<!-- mcp-name: io.github.zw008/vmware-log-insight -->

# VMware Log Insight

> **Disclaimer**: Community-maintained open-source project, **not affiliated with,
> endorsed by, or sponsored by VMware, Inc. or Broadcom Inc.** "VMware", "vSphere",
> and "Aria" are trademarks of Broadcom. Source is publicly auditable under the MIT license.

Read-only log search and aggregation for **VMware Aria Operations for Logs**
(formerly vRealize Log Insight) — the appliance that collects syslog from ESXi
hosts, vCenter, and VMs. The centralized-log data source for the VMware skill
family. **Strictly non-destructive**: it queries, it never writes.

- **Read-only by design — and provable** (v1.8.0): all 7 MCP tools are read, none write; set `VMWARE_READ_ONLY=true` (or the per-skill `VMWARE_LOG_INSIGHT_READ_ONLY`, or `read_only: true` in config) and the family read-only gate verifies that at startup instead of taking the docs' word for it. See [Read-Only Mode](#read-only-mode).

## Companion Skills

| Need | Skill | Tools |
|---|---|:-:|
| Raw centralized logs + spikes | **vmware-log-insight** (this) | 7 |
| vCenter events & alarms | [vmware-monitor](https://github.com/zw008/VMware-Monitor) | 27 |
| Metrics, anomalies, capacity | [vmware-aria](https://github.com/zw008/VMware-Aria) | 28 |
| Incident correlation / root cause | [vmware-debug](https://github.com/zw008/VMware-Debug) — feed it `log_search` output | 2 |
| VM lifecycle / operations | [vmware-aiops](https://github.com/zw008/VMware-AIops) | 49 |

## Install

```bash
uv tool install vmware-log-insight
mkdir -p ~/.vmware-log-insight
cp config.example.yaml ~/.vmware-log-insight/config.yaml   # edit host/username/provider
echo 'VMWARE_LOG_INSIGHT_PROD_PASSWORD=...' > ~/.vmware-log-insight/.env
chmod 600 ~/.vmware-log-insight/.env
vmware-log-insight doctor
```

## MCP Tools (7 — all read-only)

| Tool | What |
|---|---|
| `log_search` | Search events by time window + text + filters |
| `log_aggregate` | Count/aggregate over time bins, with z-score spike detection |
| `log_fields` | List extracted fields usable in filters |
| `log_version` | Appliance version/build |
| `alert_list` / `alert_get` / `alert_history` | Query defined alerts and their trigger history |

## Read-Only Mode

vmware-log-insight is read-only by design — all 7 MCP tools carry the `[READ]` marker and
there are no write tools to withhold. Since v1.8.0 that is **provable rather than merely
documented**: set `VMWARE_READ_ONLY=true` and the family read-only gate enumerates the
registry at startup and verifies that zero write tools are exposed — structural, not a
prompt instruction a model can ignore. **Off by default.** Fail-closed: if the mode is
requested but cannot be guaranteed, the server refuses to start rather than running open.

The same variable is family-wide: one env var also strips every write tool from the
write-capable siblings (aiops, storage, vks, nsx, ...), so a whole-estate audit posture is
a single setting.

```json
{
  "mcpServers": {
    "vmware-log-insight": {
      "command": "vmware-log-insight",
      "args": ["mcp"],
      "env": { "VMWARE_READ_ONLY": "true" }
    }
  }
}
```

- Per-skill override: `VMWARE_LOG_INSIGHT_READ_ONLY=true` (takes precedence over the family-wide `VMWARE_READ_ONLY`)
- Config alternative: `read_only: true` in `~/.vmware-log-insight/config.yaml`

Precedence: per-skill env → family env → config → off. Nothing is logged as withheld
because nothing is — the gate's empty result *is* the assertion (write-capable siblings log
`Read-only mode active ... withheld N write tool(s)` instead).

## Workflows

- **Find errors fast** — `vmware-log-insight search -q error -l 1h`.
- **Where did logs burst?** — `vmware-log-insight aggregate -q error -l 6h --bin-ms 300000`, read `spikes[]`, then `search` the spike window.
- **Root cause** — pass `log_search` results (plus vCenter events from vmware-monitor and metrics from vmware-aria) to **vmware-debug** `incident_timeline`.

## Troubleshooting

- `401 on /sessions` → check username/password/`provider` and the `VMWARE_LOG_INSIGHT_<TARGET>_PASSWORD` env var.
- `503 everywhere` → appliance starting up; `doctor` reports it as a status, not a crash.
- Empty results → widen `--last`; default API port is **9543** (set `port` if different).

## Security

Read-only by construction. Credentials in `~/.vmware-log-insight/.env` (`chmod 600`);
plaintext passwords auto-obfuscated to grep-safe `b64:` (obfuscation, not
encryption — inject from a secret manager for real secrecy). TLS on by default.
See [SECURITY.md](SECURITY.md).

## License

MIT.
