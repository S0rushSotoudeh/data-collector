import json
import math
from datetime import date, datetime, time
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

from src.analytics.parity import (
    Book, Fees, calculate, executable_capacity, margin_per_share, present_value,
    round_to_tick, validate_book,
)
from src.analytics.parity_config import ParityRunConfig
from src.analytics.parity_engine import aligned_snapshots, latest_state_rows, process_run
from src.db.clickhouse.parity import (
    RUNS_DDL,
    SNAPSHOTS_DDL,
    SNAPSHOT_COLUMNS,
    count_runs,
    count_snapshots,
    get_runs_paginated,
    get_snapshots_paginated,
)


def test_margin_units():
    assert margin_per_share(120, "per_share", 10_000, 1000) == 120
    assert margin_per_share(120_000, "per_contract", 10_000, 1000) == 120
    assert margin_per_share(2, "percent", 10_000, 1000) == 200
    assert margin_per_share(200, "basis_points", 10_000, 1000) == 200


def test_continuous_discounting():
    assert present_value(100, .1, 2) == pytest.approx(100 * math.exp(-.2))


def test_three_maker_strategies_fees_capacity_totals_and_boundaries():
    result = calculate(
        call=Book(20, 21, 8, 9), put=Book(10, 11, 7, 6),
        stock=Book(110, 111, 650, 550), strike=100, ttm_years=0,
        borrowing_rate=0.2,
        fees=Fees(stock_buy=.01, stock_sell=.01, call_buy=.02, call_sell=.02, put_buy=.03, put_sell=.03),
        required_margin=1, multiplier=100, tick_size=.5,
    )
    closing = 21 * .02 + 10 * .03 + 110 * .01
    assert result["make_call_ask_gross_edge"] == -1
    assert result["make_call_ask_estimated_closing_fee"] == pytest.approx(closing)
    assert result["make_call_ask_net_edge"] < result["make_call_ask_gross_edge"]
    assert result["make_call_ask_surplus_edge"] == pytest.approx(result["make_call_ask_net_edge"] - 1)
    assert result["make_call_ask_capacity"] == 5
    assert result["make_call_ask_limiting_legs"] == ["underlying"]
    assert result["make_put_bid_capacity"] == 5
    assert result["make_underlying_bid_capacity"] == 6
    assert result["make_call_ask_total_value"] == result["make_call_ask_surplus_edge"] * 500
    assert result["make_call_ask_suggested_maker_price"] % .5 == 0
    assert result["make_put_bid_suggested_maker_price"] % .5 == 0
    assert result["make_underlying_bid_suggested_maker_price"] % .5 == 0


def test_capacity_floors_stock_and_reports_ties():
    assert executable_capacity(5, 5, 599, 100) == (5, ["call", "put", "underlying"])


def test_maker_boundaries_are_zero_surplus_and_one_tick_beyond_is_profitable():
    common = dict(put=Book(10, 11, 20, 20), stock=Book(100, 101, 2_000, 2_000), strike=100,
                  ttm_years=0, borrowing_rate=0, fees=Fees(), required_margin=1, multiplier=100, tick_size=1)
    probe = calculate(call=Book(20, 21, 20, 20), **common)
    call_boundary = probe["make_call_ask_profitable_boundary"]
    at_boundary = calculate(call=Book(20, call_boundary, 20, 20), **common)
    beyond = calculate(call=Book(20, call_boundary + 1, 20, 20), **common)
    assert at_boundary["make_call_ask_surplus_edge"] == pytest.approx(0)
    assert not at_boundary["make_call_ask_opportunity"]
    assert beyond["make_call_ask_opportunity"]

    put_boundary = probe["make_put_bid_profitable_boundary"]
    at_boundary = calculate(call=Book(20, 21, 20, 20), put=Book(put_boundary, 11, 20, 20), **{k: v for k, v in common.items() if k != "put"})
    beyond = calculate(call=Book(20, 21, 20, 20), put=Book(put_boundary - 1, 11, 20, 20), **{k: v for k, v in common.items() if k != "put"})
    assert at_boundary["make_put_bid_surplus_edge"] == pytest.approx(0)
    assert beyond["make_put_bid_opportunity"]

    stock_boundary = probe["make_underlying_bid_profitable_boundary"]
    at_boundary = calculate(call=Book(20, 21, 20, 20), stock=Book(stock_boundary, 101, 2_000, 2_000), **{k: v for k, v in common.items() if k != "stock"})
    beyond = calculate(call=Book(20, 21, 20, 20), stock=Book(stock_boundary - 1, 101, 2_000, 2_000), **{k: v for k, v in common.items() if k != "stock"})
    assert at_boundary["make_underlying_bid_surplus_edge"] == pytest.approx(0)
    assert beyond["make_underlying_bid_opportunity"]


def test_directional_tick_rounding():
    assert round_to_tick(10.24, .5, "floor") == 10
    assert round_to_tick(10.24, .5, "ceil") == 10.5


def test_locked_allowed_crossed_rejected():
    assert validate_book(Book(10, 10, 1, 1), "call") == []
    assert "call_crossed_book" in validate_book(Book(11, 10, 1, 1), "call")


def test_interval_alignment_and_same_day_seed():
    tz = ZoneInfo("Asia/Tehran")
    points = aligned_snapshots(date(2026, 1, 1), time(8, 30, 5), time(8, 31), 30)
    assert [p.time() for p in points] == [time(8, 30, 30), time(8, 31)]
    rows = [(82959, 1), (83045, 2)]
    assert latest_state_rows(rows, points) == [rows[0], rows[1]]
    assert all(p.tzinfo == tz for p in points)


def test_process_run_persists_complete_invalid_and_valid_snapshots():
    """Exercise both snapshot branches without requiring a ClickHouse service."""
    config = {
        "underlying_instrument_code": "stock", "call_instrument_code": "call",
        "put_instrument_code": "put", "start_date": "2026-01-01", "end_date": "2026-01-01",
        "start_time": "09:00:00", "end_time": "09:01:00", "interval_seconds": 60,
        "expiry_cutoff": "12:30:00", "multiplier": 100, "margin_value": 0,
        "funding_source": "manual", "manual_borrowing_rate": 0.1,
        "strike": 100, "expiry_date": "2026-12-31",
    }
    stored = SimpleNamespace(
        column_names=["run_id", "config_json"],
        result_rows=[("00000000-0000-0000-0000-000000000001", json.dumps(config))],
    )
    client = MagicMock()

    def query(sql, parameters=None):
        if "parity_analysis_runs" in sql:
            return stored
        if "yield_curve_fits" in sql:
            return SimpleNamespace(result_rows=[])
        code = parameters["code"]
        quotes = {
            "stock": [(90100, 100, 101, 1_000, 1_000)],
            "call": [(90100, 20, 21, 10, 10)],
            "put": [(90100, 10, 11, 10, 10)],
        }
        return SimpleNamespace(result_rows=quotes[code])

    client.query.side_effect = query
    with (
        patch("src.analytics.parity_engine.get_client", return_value=client),
        patch("src.analytics.parity_engine.insert_run"),
        patch("src.analytics.parity_engine.insert_snapshots") as insert_snapshots,
    ):
        counts = process_run("00000000-0000-0000-0000-000000000001")

    assert counts == {
        "snapshot_count": 2, "valid_count": 1, "warning_count": 0,
        "invalid_count": 1, "opportunity_count": 0,
    }
    rows = insert_snapshots.call_args.args[0]
    invalid, valid = rows
    assert all(set(SNAPSHOT_COLUMNS).issubset(row) for row in rows)
    assert invalid["quality_status"] == "invalid"
    assert invalid["quality_reasons"] == [
        "missing_stock_quote", "missing_call_quote", "missing_put_quote",
    ]
    assert invalid["make_call_ask_limiting_legs"] == []
    assert invalid["make_call_ask_net_edge"] is None
    assert valid["quality_status"] == "valid"
    assert valid["make_call_ask_net_edge"] is not None


def test_config_validation_and_effective_fee_override():
    cfg = ParityRunConfig(
        underlying_instrument_code="s", call_instrument_code="c", put_instrument_code="p",
        start_date=date(2026, 1, 1), end_date=date(2026, 1, 1), multiplier=100,
        stock_buy_fee=.123,
    )
    assert cfg.effective_fees().stock_buy == .123
    with pytest.raises(ValueError):
        ParityRunConfig(
            underlying_instrument_code="s", call_instrument_code="c", put_instrument_code="p",
            start_date=date(2026, 1, 2), end_date=date(2026, 1, 1), multiplier=100,
        )


def test_parity_ddl_keys_and_engines():
    assert "ReplacingMergeTree(updated_at)" in RUNS_DDL
    assert "PARTITION BY toYYYYMM(trade_date)" in SNAPSHOTS_DDL
    assert "ORDER BY (run_id, trade_date, snapshot_time)" in SNAPSHOTS_DDL
    assert "quality_reasons Array(String)" in SNAPSHOTS_DDL


async def test_admin_run_queries_are_filtered_and_paginated(mock_async_client):
    mock_async_client.query.return_value.result_rows = [(3,)]
    assert await count_runs(run_id="run-1", status="completed") == 3
    sql = mock_async_client.query.await_args.args[0]
    params = mock_async_client.query.await_args.kwargs["parameters"]
    assert "FINAL WHERE" in sql
    assert "toString(run_id)" in sql
    assert params == {"run_id": "run-1", "status": "completed"}

    result = type("Result", (), {
        "column_names": ["run_id", "status"],
        "result_rows": [("run-1", "completed")],
    })()
    mock_async_client.query.return_value = result
    rows = await get_runs_paginated(offset=100, limit=25)
    assert rows == [{"run_id": "run-1", "status": "completed"}]
    assert mock_async_client.query.await_args.kwargs["parameters"] == {
        "limit": 25,
        "offset": 100,
    }


async def test_admin_snapshot_opportunity_filters_handle_zero(mock_async_client):
    mock_async_client.query.return_value.result_rows = [(2,)]
    assert await count_snapshots(opportunity=0) == 2
    sql = mock_async_client.query.await_args.args[0]
    assert "make_call_ask_opportunity = {opportunity:UInt8} AND" in sql
    assert mock_async_client.query.await_args.kwargs["parameters"]["opportunity"] == 0

    result = type("Result", (), {
        "column_names": ["run_id", "quality_status"],
        "result_rows": [("run-1", "valid")],
    })()
    mock_async_client.query.return_value = result
    rows = await get_snapshots_paginated(opportunity=1, limit=10)
    assert rows == [{"run_id": "run-1", "quality_status": "valid"}]
    assert "make_call_ask_opportunity = {opportunity:UInt8} OR" in mock_async_client.query.await_args.args[0]


def test_parity_admin_templates_compile():
    from src.admin._render import _TEMPLATE_ENV

    _TEMPLATE_ENV.get_template("option/parity_runs_list.html")
    _TEMPLATE_ENV.get_template("option/parity_snapshots_list.html")
