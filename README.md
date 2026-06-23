<!-- mcp-name: io.github.zw008/vmware-log-insight -->

# VMware Log Insight

> **Disclaimer**: Community-maintained open-source project, **not affiliated with,
> endorsed by, or sponsored by VMware, Inc. or Broadcom Inc.** "VMware", "vSphere",
> and "Aria" are trademarks of Broadcom. Source is publicly auditable under the MIT license.

Read-only log search and aggregation for **VMware Aria Operations for Logs**
(formerly vRealize Log Insight) — the appliance that collects syslog from ESXi
hosts, vCenter, and VMs. The centralized-log data source for the VMware skill
family. **Strictly non-destructive**: it queries, it never writes.

## Companion Skills

| Need | Skill |
|---|---|
| Raw centralized logs + spikes | **vmware-log-insight** (this) |
| vCenter events & alarms | [vmware-monitor](https://github.com/zw008/VMware-Monitor) |
| Metrics, anomalies, capacity | [vmware-aria](https://github.com/zw008/VMware-Aria) |
| Incident correlation / root cause | [vmware-debug](https://github.com/zw008/VMware-Debug) — feed it `log_search` output |
| VM lifecycle / operations | [vmware-aiops](https://github.com/zw008/VMware-AIops) |

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
