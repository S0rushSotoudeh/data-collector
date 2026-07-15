import json
import math
from datetime import date, datetime, time
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

from src.analytics.parity import (
    CALCULATION_VERSION, Book, Fees, calculate, executable_capacity, margin_per_share, present_value,
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
        stock=Book(110, 111, 650, 550), strike=100, ttm_years=1,
        borrowing_rate=0.2,
        fees=Fees(stock_buy=.01, stock_sell=.01, call_buy=.02, call_sell=.02, put_buy=.03, put_sell=.03),
        minimum_ytm_spread_bps=100, multiplier=100, tick_size=.5,
    )
    capital = 111 * 1.01 + 11 * 1.03 - 21 * (1 - .02)
    assert result["make_call_ask_capital_per_share"] == pytest.approx(capital)
    assert result["make_call_ask_capital_per_contract"] == pytest.approx(capital * 100)
    assert result["make_call_ask_expiry_profit_per_share"] == pytest.approx(100 - capital)
    assert result["make_call_ask_holding_return"] == pytest.approx(100 / capital - 1)
    assert result["make_call_ask_ytm"] == pytest.approx(math.log(100 / capital))
    assert result["make_call_ask_ytm_spread_bps"] == pytest.approx((math.log(100 / capital) - .2) * 10_000)
    assert result["target_ytm"] == pytest.approx(.21)
    assert result["target_capital_per_share"] == pytest.approx(100 * math.exp(-.21))
    assert result["make_call_ask_capacity"] == 5
    assert result["make_call_ask_limiting_legs"] == ["underlying"]
    assert result["make_put_bid_capacity"] == 5
    assert result["make_underlying_bid_capacity"] == 6
    assert result["make_call_ask_total_capital"] == pytest.approx(capital * 500)
    assert result["make_call_ask_total_expiry_profit"] == pytest.approx((100 - capital) * 500)
    suggestions = [result[f"{strategy}_suggested_maker_price"] for strategy in (
        "make_call_ask", "make_put_bid", "make_underlying_bid"
    )]
    assert any(value is not None for value in suggestions)
    assert all(value % .5 == 0 for value in suggestions if value is not None)


def test_capacity_floors_stock_and_reports_ties():
    assert executable_capacity(5, 5, 599, 100) == (5, ["call", "put", "underlying"])


def test_maker_boundaries_hit_target_ytm_and_ticks_change_opportunity():
    common = dict(put=Book(5, 11, 20, 20), stock=Book(100, 101, 2_000, 2_000), strike=100,
                  ttm_years=1, borrowing_rate=.05, fees=Fees(), minimum_ytm_spread_bps=100,
                  multiplier=100, tick_size=1)
    probe = calculate(call=Book(10, 20, 20, 20), **common)
    call_boundary = probe["make_call_ask_target_boundary"]
    at_boundary = calculate(call=Book(10, call_boundary, 20, 20), **common)
    adverse = calculate(call=Book(10, call_boundary - 1, 20, 20), **common)
    assert at_boundary["make_call_ask_ytm"] == pytest.approx(.06)
    assert at_boundary["make_call_ask_opportunity"]
    assert not adverse["make_call_ask_opportunity"]

    put_boundary = probe["make_put_bid_target_boundary"]
    at_boundary = calculate(call=Book(10, 20, 20, 20), put=Book(put_boundary, 11, 20, 20), **{k: v for k, v in common.items() if k != "put"})
    adverse = calculate(call=Book(10, 20, 20, 20), put=Book(put_boundary + 1, 11, 20, 20), **{k: v for k, v in common.items() if k != "put"})
    assert at_boundary["make_put_bid_ytm"] == pytest.approx(.06)
    assert at_boundary["make_put_bid_opportunity"]
    assert not adverse["make_put_bid_opportunity"]

    stock_boundary = probe["make_underlying_bid_target_boundary"]
    at_boundary = calculate(call=Book(10, 20, 20, 20), stock=Book(stock_boundary, 101, 2_000, 2_000), **{k: v for k, v in common.items() if k != "stock"})
    adverse = calculate(call=Book(10, 20, 20, 20), stock=Book(stock_boundary + 1, 101, 2_000, 2_000), **{k: v for k, v in common.items() if k != "stock"})
    assert at_boundary["make_underlying_bid_ytm"] == pytest.approx(.06)
    assert at_boundary["make_underlying_bid_opportunity"]
    assert not adverse["make_underlying_bid_opportunity"]


def test_opening_credit_is_an_opportunity_with_undefined_ratio_metrics():
    result = calculate(
        call=Book(120, 121, 5, 5), put=Book(1, 2, 5, 5), stock=Book(10, 11, 500, 500),
        strike=100, ttm_years=.25, borrowing_rate=.2, fees=Fees(),
        minimum_ytm_spread_bps=0, multiplier=100,
    )
    assert result["make_call_ask_capital_per_share"] < 0
    assert result["make_call_ask_ytm"] is None
    assert result["make_call_ask_holding_return"] is None
    assert result["make_call_ask_opportunity"]


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
        "expiry_cutoff": "12:30:00", "multiplier": 100, "minimum_ytm_spread_bps": 0,
        "funding_source": "manual", "manual_borrowing_rate": 0.1,
        "strike": 100, "expiry_date": "2026-12-31",
    }
    stored = SimpleNamespace(
        column_names=["run_id", "config_json", "calculation_version"],
        result_rows=[("00000000-0000-0000-0000-000000000001", json.dumps(config), CALCULATION_VERSION)],
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
    assert valid["make_call_ask_capital_per_contract"] is not None
    assert valid["make_call_ask_expiry_profit_per_contract"] is not None
    assert valid["make_call_ask_ytm"] is not None


def test_process_run_uses_ask_curve_for_borrowing_rate():
    config = {
        "underlying_instrument_code": "stock", "call_instrument_code": "call",
        "put_instrument_code": "put", "start_date": "2026-01-01", "end_date": "2026-01-01",
        "start_time": "09:01:00", "end_time": "09:01:00", "interval_seconds": 60,
        "expiry_cutoff": "12:30:00", "multiplier": 100, "minimum_ytm_spread_bps": 0,
        "funding_source": "curve", "strike": 100, "expiry_date": "2026-12-31",
    }
    stored = SimpleNamespace(
        column_names=["run_id", "config_json", "calculation_version"],
        result_rows=[("00000000-0000-0000-0000-000000000001", json.dumps(config), CALCULATION_VERSION)],
    )
    client = MagicMock()

    def query(sql, parameters=None):
        if "parity_analysis_runs" in sql:
            return stored
        if "yield_curve_fits" in sql:
            return SimpleNamespace(result_rows=[
                (90100, "bid", 0.10, 0.0, 0.0, 1.0, 0.0, 4, 1),
                (90100, "ask", 0.20, 0.0, 0.0, 1.0, 0.0, 4, 1),
            ])
        quotes = {
            "stock": [(90100, 100, 101, 1_000, 1_000)],
            "call": [(90100, 20, 21, 10, 10)],
            "put": [(90100, 10, 11, 10, 10)],
        }
        return SimpleNamespace(result_rows=quotes[parameters["code"]])

    client.query.side_effect = query
    with (
        patch("src.analytics.parity_engine.get_client", return_value=client),
        patch("src.analytics.parity_engine.insert_run"),
        patch("src.analytics.parity_engine.insert_snapshots") as insert_snapshots,
    ):
        process_run("00000000-0000-0000-0000-000000000001")

    row = insert_snapshots.call_args.args[0][0]
    assert row["borrowing_rate"] == pytest.approx(0.20)
    assert row["borrowing_beta0"] == pytest.approx(0.20)
    assert row["borrowing_source"] == "curve"


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
    assert "minimum_ytm_spread_bps Nullable(Float64)" in RUNS_DDL
    assert "make_call_ask_capital_per_contract Nullable(Float64)" in SNAPSHOTS_DDL
    assert "make_underlying_bid_ytm_spread_bps Nullable(Float64)" in SNAPSHOTS_DDL


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
