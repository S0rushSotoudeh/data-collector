# Data Collector for HFT Analytics

High-frequency market data aggregation platform. Collects real-time tick data from Iran stocks (TSETMC), crypto exchanges (Binance, Nobitex, Wallex), and Iranian bonds (اخزا). Streams via Redis → stores in ClickHouse (time-series) + PostgreSQL (metadata) → serves via FastAPI → displays on React + TradingView charts.

## Non-negotiable rules

- **All code runs inside Docker Compose** — never run Python directly on host. Use `docker compose exec api ...` for everything.
- **Admin BaseView pages** must use manual `jinja2.Environment` + `_render()` helper with `self._admin_ref` (never `self.admin`). See `.kilo/agent/admin-panel.md`.
- **Prefix all shell commands with `rtk`** — saves 60-90% tokens. See `.kilo/rules/rtk-rules.md`.

## Reference files

| File | What's inside |
|------|---------------|
| `.kilo/agent/overview.md` | Architecture diagram, data flow, design philosophy |
| `.kilo/agent/stack.md` | Technology stack table |
| `.kilo/agent/status.md` | Implementation status, current state, PG + CH schemas |
| `.kilo/agent/structure.md` | Full project directory tree |
| `.kilo/agent/dev-workflow.md` | Docker, test, migration CLI commands |
| `.kilo/agent/admin-panel.md` | Admin panel template pattern, context keys, how-to-add |
