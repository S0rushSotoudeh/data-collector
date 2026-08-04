# Data Collector for HFT Analytics

High-frequency market data aggregation platform. Collects real-time tick data from Iran stocks (TSETMC), crypto exchanges (Binance, Nobitex, Wallex), and Iranian bonds (اخزا). Streams via Redis → stores in ClickHouse (time-series) + PostgreSQL (metadata) → serves via FastAPI → displays on React + TradingView charts.

## Non-negotiable rules

- **All code runs inside Docker Compose** — never run Python directly on host. Use `docker compose exec api ...` for everything.
- **Admin BaseView pages** must use manual `jinja2.Environment` + `_render()` helper with `self._admin_ref` (never `self.admin`). See `.kilo/agent/admin-panel.md`.
- **Graphify is mandatory for code work.** Before reading implementation files or editing code, follow `.agents/skills/graphify/SKILL.md`: verify graph freshness, update it when stale, and query the affected subsystem. After every code change, update the graph and query the changed symbols again. If Graphify is unavailable or fails, stop and report the failure instead of silently substituting raw search.

## Reference files

| File | What's inside |
|------|---------------|
| `.kilo/agent/overview.md` | Architecture diagram, data flow, design philosophy |
| `.kilo/agent/stack.md` | Technology stack table |
| `.kilo/agent/status.md` | Implementation status, current state, PG + CH schemas |
| `.kilo/agent/structure.md` | Full project directory tree |
| `.kilo/agent/dev-workflow.md` | Docker, test, migration CLI commands |
| `.kilo/agent/admin-panel.md` | Admin panel template pattern, context keys, how-to-add |
| `.agents/skills/graphify/SKILL.md` | Required graph-first code discovery and post-change update workflow |
