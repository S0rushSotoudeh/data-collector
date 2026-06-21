# Data Collector for HFT Analytics

High-frequency market data aggregation platform. Collects real-time tick data from Iran stocks (TSETMC), crypto exchanges (Binance, Nobitex, Wallex), and Iranian bonds (اخزا). Streams via Redis → stores in ClickHouse (time-series) + PostgreSQL (metadata) → serves via FastAPI → displays on React + TradingView charts.

## Non-negotiable rules

- **All code runs inside Docker Compose** — never run Python directly on host. Use `docker compose exec api ...` for everything.
- **Admin BaseView pages** must use manual `jinja2.Environment` + `_render()` helper with `self._admin_ref` (never `self.admin`). See `.kilo/agent/admin-panel.md`.
- **Prefix all shell commands with `rtk`** — saves 60-90% tokens. See `.kilo/rules/rtk-rules.md`.

## Reference files

| File | What's inside |
|------|---------------|
| `./agent/overview.md` | Architecture diagram, data flow, design philosophy |
| `./agent/stack.md` | Technology stack table |
| `./agent/status.md` | Implementation status, current state, PG + CH schemas |
| `./agent/structure.md` | Full project directory tree |
| `./agent/dev-workflow.md` | Docker, test, migration CLI commands |
| `./agent/admin-panel.md` | Admin panel template pattern, context keys, how-to-add |
