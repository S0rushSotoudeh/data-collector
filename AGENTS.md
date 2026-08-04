# Data Collector for HFT Analytics

High-frequency market data aggregation platform. Collects real-time tick data from Iran stocks (TSETMC), crypto exchanges (Binance, Nobitex, Wallex), and Iranian bonds (اخزا). Streams via Redis → stores in ClickHouse (time-series) + PostgreSQL (metadata) → serves via FastAPI → displays on React + TradingView charts.

## Non-negotiable rules

- **All application code runs inside Docker Compose** — never run application Python directly on the host. Use `docker compose exec api ...` for application commands. Graphify is repository tooling and is the explicit exception described below.
- **Admin BaseView pages** must use manual `jinja2.Environment` + `_render()` helper with `self._admin_ref` (never `self.admin`). See `.kilo/agent/admin-panel.md`.
- **Graphify is mandatory for code work and must be invoked from the repository virtual environment.** Do not rely on `graphify` being available on `PATH` and do not run it inside Docker. From the repository root on Windows/PowerShell, always invoke it as `& .\.venv\Scripts\graphify.exe <command>` (for example, `& .\.venv\Scripts\graphify.exe update .` and `& .\.venv\Scripts\graphify.exe query "<question>"`). Before reading implementation files or editing code, follow `.agents/skills/graphify/SKILL.md`: verify graph freshness, update it when stale, and query the affected subsystem. After every code change, update the graph with the same `.venv` executable and query the changed symbols again. If that executable is missing or the command fails, stop and report the failure instead of silently substituting raw search.

## Reference files

| File | What's inside |
|------|---------------|
| `.kilo/agent/overview.md` | Architecture diagram, data flow, design philosophy |
| `.kilo/agent/stack.md` | Technology stack table |
| `.kilo/agent/status.md` | Implementation status, current state, PG + CH schemas |
| `.kilo/agent/dev-workflow.md` | Docker, test, migration CLI commands |
| `.kilo/agent/admin-panel.md` | Admin panel template pattern, context keys, how-to-add |
| `.agents/skills/graphify/SKILL.md` | Required graph-first code discovery and post-change update workflow |
