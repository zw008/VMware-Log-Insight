## v1.8.0 (2026-07-18) — read-only mode, working policy defaults, declared environments

Family release driven by [VMware-AIops#31](https://github.com/zw008/VMware-AIops/issues/31),
where an operator running Llama 3.3 70B (Goose / OpenShift AI, on-prem H100) had to
hand-write 17 prompt guardrails to make tool calling reliable. A prompt is advisory — a
model can ignore it. Every guardrail that could move into the harness has.

### Added
- **Read-only mode.** Set `VMWARE_READ_ONLY=true` (or `VMWARE_<SKILL>_READ_ONLY`, or
  `read_only: true` in config.yaml) and every write tool is removed from the MCP registry
  at start-up. `list_tools()` never offers them, so the model cannot call what it cannot
  see. **Off by default** — nothing changes unless you turn it on. Fail-closed: if the
  mode is requested but cannot be guaranteed, the server refuses to start rather than
  running open.
- **`environment:` on each config target**, declaring which environment it is
  (production / staging / lab). Policy rules scope by this value.

### Added — list results now state whether they are complete

Every `[READ]` list tool returns the family envelope instead of a bare array:

    {"items": [...], "returned": 50, "limit": 50, "total": 213,
     "truncated": true, "hint": "Showing 50 of 213. Raise limit or narrow the query..."}

This closes the reported failure where long responses were summarised as "no data
returned": a bare list gives a model no way to tell a complete answer from page one, so
it guessed. `truncated: false` now positively states completeness — including when
`items` is empty, which means "checked, found none", not "the call failed".

- **3 tool(s) converted** across ops, MCP and CLI. Real totals at no extra cost: the appliance returns each collection in one GET and the
  limit was applied client-side, so the match count was already in memory. `alert_list`
  counts matches, respecting `name_filter`.

### Changed — migration, read this
- **Approval tiers now actually run.** They shipped in v1.6.0 but the engine only ever
  read `~/.vmware/rules.yaml`, and a fresh install has no such file — so every deny rule,
  maintenance window and approval tier had been inert on every install that never
  hand-authored one. A packaged baseline now loads when you have written no rules of your
  own. Writes at medium risk and above are stamped with their tier in the audit log;
  irreversible work and guest execution against a target declared `production` require a
  named approver via `VMWARE_AUDIT_APPROVED_BY`.
- **`environment:` will become required for writes.** Today a state-changing operation
  against a target that declares none still runs and logs a warning. **The next major
  release refuses it.** Declare it now and that upgrade is a no-op:

      targets:
        prod-vc01:
          host: vc01.corp.local
          environment: production

  Read-only operations are never affected, in this release or the next. Check what applies
  to your targets before upgrading: `vmware-audit policy --operation vm_delete --env <env>`.

### Fixed
- **Policy glob patterns with a leading wildcard silently matched nothing.** A rule written
  `operations: ["*_delete"]` parsed fine, read correctly, and never fired — only a trailing
  `*` was honoured. Now full glob matching, for operations and environments alike.
- Config-path overrides (`VMWARE_<SKILL>_CONFIG`) are honoured when reading `read_only`
  and `environment`, so a setting in a custom config file is no longer silently ignored.

### Notes
- Requires `vmware-policy>=1.8.0`; publish that package first.
- `vmware-audit policy` reports which rules are in force and where they came from —
  including the case where your rules file exists but failed to parse, which previously
  looked identical to "policy is working".

## v1.6.1 (2026-06-24) — initial release

First release of **vmware-log-insight**: read-only log search and aggregation for
VMware Aria Operations for Logs (vRealize Log Insight). The centralized-log data
source for the VMware skill family.

### Added
- **7 read-only MCP tools**: `log_search` (time-window + text + filter event
  search), `log_aggregate` (COUNT/UCOUNT/AVG/… time series with z-score spike
  detection), `log_fields`, `log_version`, `alert_list`, `alert_get`,
  `alert_history`.
- **Typer CLI** mirroring the tools: `search`, `aggregate`, `fields`,
  `alert list/get/history`, `doctor`, `mcp`, `version`.
- **Session auth** (`POST /api/v2/sessions`, Bearer token, TTL refresh) with
  **centralized HTTP error translation** to teaching `LogInsightApiError`
  (status + path + fix hint); transient 502/503/504 + transport errors retry once,
  401 re-auths once, 4xx are not retried (CLAUDE.md 错误恢复三层 / 踩坑 #37).
- **Path-encoded constraint builder** with human duration shorthand ("1h", "30m",
  "7d") and URL-escaped values; never issues an unbounded query (defaults to last hour).
- **`.env` password obfuscation** built in from day one: plaintext `*_PASSWORD`
  auto-rewritten to grep-safe `b64:` via python-dotenv's own parser (obfuscation,
  not encryption; secret-manager injection documented). CLAUDE.md 踩坑 #38.
- **Spec-conformance test** (踩坑 #36): AST-scans every HTTP call against the
  official API index in `tests/eval/spec/` so a hallucinated endpoint fails CI.
- Regression evals: MCP tool exposure (踩坑 #34), read-only invariant, b64 parity.

### Notes
- Strictly **read-only** — no ingest/write tools.
- Exact v2 response schemas are parsed defensively across documented wire variants;
  confirmation against a live appliance's `/rest-api` reference is tracked in BACKLOG
  (same real-hardware-verification status as VKS `/wcp/login`).
