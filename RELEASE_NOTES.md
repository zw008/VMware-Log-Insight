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
