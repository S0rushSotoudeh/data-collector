import json
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from urllib.parse import parse_qs, urlencode

import jinja2
import pytest
from starlette.requests import Request

from src.admin import market_data as admin
from src.admin._render import _TEMPLATE_ENV
from src.admin.bonds.clickhouse_views import BondOrderBookView, BondTradesView
from src.admin.gold.views import GoldOrderBookView, GoldTradesView
from src.admin.option.option_clickhouse_views import OptionOrderBookView, OptionTradesView
from src.admin.stock.stock_clickhouse_views import StockOrderBookView, StockTradesView
from src.db.clickhouse import market_data as db


VIEWS = [BondOrderBookView, BondTradesView, GoldOrderBookView, GoldTradesView,
         OptionOrderBookView, OptionTradesView, StockOrderBookView, StockTradesView]
DAY = date(2026, 8, 11)


def request(**params):
    return Request({"type": "http", "method": "GET", "path": "/admin/stock-trades",
                    "query_string": urlencode(params).encode(), "headers": []})


@pytest.fixture
def rendered(monkeypatch):
    contexts = []
    env = _TEMPLATE_ENV.overlay(loader=jinja2.ChoiceLoader([
        jinja2.DictLoader({"shared/admin_base.html": "{% block content %}{% endblock %}"}),
        _TEMPLATE_ENV.loader,
    ]))

    def render(template, ctx):
        contexts.append(ctx)
        return env.get_template(template).render(ctx)

    monkeypatch.setattr(admin, "_render", render)
    return contexts


def rows(count, start=0):
    return [dict(instrument_code="123", trade_date=DAY, trade_time=34200,
                 trade_id=i, depth_level=i, price=100, value=100, volume=1,
                 bid_price=100, ask_price=101, bid_volume=1, ask_volume=1,
                 bid_order_count=1, ask_order_count=1, data_source="tsetmc")
            for i in range(start, start + count)]


@pytest.mark.parametrize("view_type", VIEWS)
async def test_all_market_views_render_without_counts(view_type, rendered):
    view = view_type()
    view._admin_ref = None
    data = rows(101)
    if "Trades" in view_type.__name__:
        for row in data:
            row.pop("depth_level")
    with patch.object(admin, "latest_market_date", AsyncMock(return_value=DAY)) as latest, \
         patch.object(admin, "market_data_page", AsyncMock(return_value=data)) as fetch:
        response = await view._list(request(instrument_code="123", page="99999999"))
    assert response.status_code == 200
    latest.assert_awaited_once_with(view.table_name)
    assert fetch.call_args.args[-1] == 101
    assert fetch.call_args.args[1]["trade_date"] == DAY
    ctx = rendered[-1]
    assert len(ctx["rows"]) == 100 and ctx["prev_url"] is None
    params = parse_qs(ctx["next_url"][1:])
    assert params["trade_date"] == [DAY.isoformat()]
    assert "page" not in params
    assert json.loads(params["after"][0]) == [34200, "123", 99]
    assert "total" not in ctx
    assert b"100 records shown" in response.body
    assert b"Next" in response.body


@pytest.mark.parametrize("size", [0, 7, 100])
async def test_last_page_and_empty_result(size, rendered):
    view = StockTradesView()
    view._admin_ref = None
    with patch.object(admin, "market_data_page", AsyncMock(return_value=rows(size))), \
         patch.object(admin, "latest_market_date", AsyncMock()) as latest:
        response = await view._list(request(trade_date=DAY.isoformat()))
    assert response.status_code == 200
    latest.assert_not_awaited()
    assert rendered[-1]["next_url"] is None


async def test_previous_page_reverses_after_trimming_extra_row(rendered):
    view = StockTradesView()
    view._admin_ref = None
    with patch.object(admin, "market_data_page", AsyncMock(return_value=list(reversed(rows(101))))) as fetch:
        response = await view._list(request(trade_date=DAY.isoformat(), before='[34200,"123",101]'))
    assert response.status_code == 200
    assert fetch.call_args.args[2:4] == ((34200, "123", 101), True)
    ctx = rendered[-1]
    assert [row["trade_id"] for row in ctx["rows"]] == list(range(1, 101))
    assert ctx["next_url"] and ctx["prev_url"]


@pytest.mark.parametrize("params", [
    {"trade_date": "bad"}, {"trade_date": "2026-02-30"},
    {"trade_date": "2026-08-11", "after": "null"},
    {"trade_date": "2026-08-11", "after": '[true,"123",1]'},
    {"trade_date": "2026-08-11", "after": '[1,"123",-1]'},
    {"trade_date": "2026-08-11", "after": '[1,"123",18446744073709551616]'},
    {"trade_date": "2026-08-11", "after": "x" * 1025},
    {"after": '[1,"123",1]'},
    {"before": "[]", "after": "[]"},
])
async def test_invalid_date_or_cursor_never_queries_history(params):
    with patch.object(admin, "market_data_page", AsyncMock()) as fetch, \
         patch.object(admin, "latest_market_date", AsyncMock()) as latest:
        response = await StockTradesView()._list(request(**params))
    assert response.status_code == 400
    fetch.assert_not_awaited()
    latest.assert_not_awaited()


async def test_empty_table_does_not_fall_back_to_unfiltered_query(rendered):
    view = StockTradesView()
    view._admin_ref = None
    with patch.object(admin, "latest_market_date", AsyncMock(return_value=None)), \
         patch.object(admin, "market_data_page", AsyncMock()) as fetch:
        response = await view._list(request())
    assert response.status_code == 200
    fetch.assert_not_awaited()
    assert rendered[-1]["rows"] == []


async def test_latest_date_reads_only_newest_partition():
    client = SimpleNamespace(query=AsyncMock(side_effect=[
        SimpleNamespace(result_rows=[("202608",)]), SimpleNamespace(result_rows=[(DAY,)]),
    ]))
    with patch.object(db, "get_async_client", AsyncMock(return_value=client)):
        assert await db.latest_market_date("stock_trades") == DAY
    first, second = client.query.call_args_list
    assert "system.parts" in first.args[0]
    assert "toYYYYMM(trade_date) = {month:UInt32}" in second.args[0]
    assert second.kwargs["parameters"] == {"month": 202608}


@pytest.mark.parametrize("table", list(db._TABLES))
@pytest.mark.parametrize("backwards", [False, True])
async def test_sql_is_bounded_deduplicated_and_uses_stable_cursor(table, backwards):
    client = SimpleNamespace(query=AsyncMock(return_value=SimpleNamespace(result_rows=[])))
    with patch.object(db, "get_async_client", AsyncMock(return_value=client)):
        await db.market_data_page(table, {"trade_date": DAY}, (34200, "x' OR 1=1", 5), backwards)
    sql = client.query.call_args.args[0]
    params = client.query.call_args.kwargs["parameters"]
    assert "FINAL WHERE trade_date = {dt:Date}" in sql
    assert "OFFSET" not in sql and "count(" not in sql and "SELECT *" not in sql
    assert "LIMIT {limit:UInt32}" in sql and params["limit"] == 101
    assert params["cursor_time"] == -34200 and params["cursor_code"] == "x' OR 1=1"
    assert "OR 1=1" not in sql
    assert ("< tuple" if backwards else "> tuple") in sql


async def test_query_requires_date():
    with pytest.raises(ValueError, match="trade date"):
        await db.market_data_page("stock_trades", {})
