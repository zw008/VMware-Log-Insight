<!-- mcp-name: io.github.zw008/vmware-log-insight -->

# VMware Log Insight

> ⚠️ **Work in progress — scaffold only.** So far this repo contains the official
> API spec index (`tests/eval/spec/api_index.py`) used to keep the client honest
> per the family's spec-conformance discipline. The REST client, ops, MCP tools,
> CLI, and docs are not written yet. Not published to PyPI.

> **Disclaimer**: Community-maintained open-source project, **not affiliated with,
> endorsed by, or sponsored by VMware, Inc. or Broadcom Inc.** "VMware",
> "vSphere", and "Aria" are trademarks of Broadcom. Source is publicly auditable
> under the MIT license.

A read-only skill for **VMware Aria Operations for Logs** (formerly vRealize Log
Insight) — the family's centralized-log data source. Planned tools: `log_search`,
`log_aggregate` (spike detection), `log_list_fields`, `log_query_alerts`. It will
be a primary data source for `vmware-debug`'s incident correlation.

## License

MIT.
