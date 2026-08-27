import json
from datetime import date, datetime, time
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest

from src.analytics.box_spread import BOX_CALCULATION_VERSION, calculate_maker_routes, price_box
from src.analytics.box_spread_config import BoxCalculatorRequest, BoxSpreadRunConfig
from src.analytics.box_spread_engine import _states, process_run
from src.analytics.depth import DepthBook, DepthLevel
from src.db.clickhouse.box_spread import PRICING_COLUMNS, SNAPSHOT_COLUMNS
from src.db.clickhouse.migrations.manager import _discover_versions


TEHRAN = ZoneInfo("Asia/Tehran")
CONVENTION_ID = UUID("00000000-0000-0000-0000-000000000010")


def book(bid=10.0, ask=11.0, bid_volume=20, ask_volume=20, second_volume=10):
    return DepthBook(datetime(2026, 7, 1, 9, 0, tzinfo=TEHRAN), (
        DepthLevel(1, bid, bid_volume, 2, ask, ask_volume, 2),
        DepthLevel(2, bid - 1, second_volume, 1, ask + 1, second_volume, 1),
    ))


def test_depth_vwap_and_capacity():
    value = book(10, 11, 2, 2, 3)
    assert value.vwap("buy", 4) == pytest.approx((2 * 11 + 2 * 12) / 4)
    assert value.vwap("sell", 4) == pytest.approx((2 * 10 + 2 * 9) / 4)
    assert value.vwap("buy", 6) is None
    assert value.total_volume("buy") == 5
    assert value.fills("buy", 4) == [(1, 11.0, 2), (2, 12.0, 2)]


def test_depth_state_carries_levels_forward_and_uses_level_one_time():
    snapshots = [
        datetime(2026, 7, 1, 9, 0, tzinfo=TEHRAN),
        datetime(2026, 7, 1, 9, 0, 30, tzinfo=TEHRAN),
    ]
    events = [
        (85950, DepthLevel(2, 9, 4, 1, 12, 5, 1)),
        (85958, DepthLevel(1, 10, 2, 1, 11, 3, 1)),
        (90015, DepthLevel(2, 8, 7, 1, 13, 8, 1)),
    ]
    states = _states(events, snapshots)
    assert states[0] is not None and states[1] is not None
    assert [level.level for level in states[0].levels] == [1, 2]
    assert states[0].source_time.time() == time(8, 59, 58)
    assert states[1].source_time == states[0].source_time
    assert states[1].levels[1].ask_price == 13


def test_prices_two_taker_and_eight_any_maker_cases():
    rows = price_box(
        books={"c1": book(12, 13), "c2": book(7, 8), "p1": book(2, 3), "p2": book(6, 7)},
        lower_strike=100, upper_strike=110, target_boxes=2, multiplier=1000,
        ttm_years=.5, benchmark_rate=.2, minimum_ytm_spread_bps=100,
        buy_fee=.001, sell_fee=.001, settlement_cost_per_contract=0,
        tick_size=1, calculated_at=datetime.now(TEHRAN),
    )
    assert len(rows) == 10
    assert {(row["direction"], row["execution_mode"]) for row in rows if row["execution_mode"] == "take_all"} == {
        ("long", "take_all"), ("short", "take_all")
    }
    maker_rows = [row for row in rows if row["execution_mode"] == "one_maker"]
    assert {(row["direction"], row["maker_leg"]) for row in maker_rows} == {
        (direction, leg) for direction in ("long", "short") for leg in ("c1", "c2", "p1", "p2")
    }
    assert all(row["capacity_boxes"] == 30 for row in rows)
    assert all(row["queue_ahead_volume"] == 20 for row in maker_rows)


def test_config_validates_strikes_dates_and_manual_funding():
    common = dict(
        trade_date=date(2026, 7, 1), underlying_instrument_code="stock", expiry_date=date(2026, 8, 1),
        lower_strike=100, upper_strike=110, pricing_convention_id=CONVENTION_ID,
    )
    assert BoxSpreadRunConfig(**common).target_box_count == 1
    assert BoxSpreadRunConfig(**(common | {"max_cross_leg_skew_seconds": 1800})).max_cross_leg_skew_seconds == 1800
    with pytest.raises(ValueError):
        BoxSpreadRunConfig(**(common | {"max_cross_leg_skew_seconds": 1801}))
    with pytest.raises(ValueError):
        BoxSpreadRunConfig(**(common | {"upper_strike": 90}))
    with pytest.raises(ValueError):
        BoxSpreadRunConfig(**(common | {"funding_source": "manual"}))


def test_engine_persists_snapshot_and_ten_pricings():
    config = BoxSpreadRunConfig(
        trade_date=date(2026, 7, 1), underlying_instrument_code="stock", expiry_date=date(2026, 8, 1),
        lower_strike=100, upper_strike=110, target_box_count=1,
        session_start=time(9), session_end=time(9), interval_seconds=30,
        pricing_convention_id=CONVENTION_ID, funding_source="manual", manual_funding_rate=.2,
    )
    stored = {
        "run_id": "00000000-0000-0000-0000-000000000001", "calculation_version": BOX_CALCULATION_VERSION,
        "config_json": config.model_dump_json(), "multiplier": 1000, "tick_size": 1,
        **{f"{leg}_instrument_code": leg for leg in ("c1", "c2", "p1", "p2")},
    }
    client = MagicMock()

    def query(sql, parameters=None):
        if "option_order_book" in sql:
            prices = {"c1": (12, 13), "c2": (7, 8), "p1": (2, 3), "p2": (6, 7)}
            return SimpleNamespace(result_rows=[
                (code, 90000, 1, bid, 20, 2, ask, 20, 2) for code, (bid, ask) in prices.items()
            ])
        return SimpleNamespace(result_rows=[])

    client.query.side_effect = query
    with (
        patch("src.analytics.box_spread_engine.get_client", return_value=client),
        patch("src.analytics.box_spread_engine._run_row", return_value=stored),
        patch("src.analytics.box_spread_engine.update_run"),
        patch("src.analytics.box_spread_engine.insert_snapshots") as snapshots,
        patch("src.analytics.box_spread_engine.insert_pricings") as pricings,
        patch("src.analytics.box_spread_engine.RunProgressReporter"),
    ):
        counts = process_run(stored["run_id"])
    assert counts["snapshot_count"] == 1
    assert counts["valid_count"] == 1
    assert counts["pricing_count"] == 10
    snapshot_rows = snapshots.call_args.args[0]
    pricing_rows = pricings.call_args.args[0]
    assert len(snapshot_rows) == 1 and set(SNAPSHOT_COLUMNS).issubset(snapshot_rows[0])
    assert len(pricing_rows) == 10 and all(set(PRICING_COLUMNS).issubset(row) for row in pricing_rows)


def test_engine_prices_each_interval_indicatively_when_only_skew_gate_fails():
    config = BoxSpreadRunConfig(
        trade_date=date(2026, 7, 1), underlying_instrument_code="stock", expiry_date=date(2026, 8, 1),
        lower_strike=100, upper_strike=110, target_box_count=1,
        session_start=time(9), session_end=time(9, 0, 30), interval_seconds=30,
        max_quote_age_seconds=60, max_cross_leg_skew_seconds=2,
        pricing_convention_id=CONVENTION_ID, funding_source="manual", manual_funding_rate=.2,
    )
    stored = {
        "run_id": "00000000-0000-0000-0000-000000000002", "calculation_version": BOX_CALCULATION_VERSION,
        "config_json": config.model_dump_json(), "multiplier": 1000, "tick_size": 1,
        **{f"{leg}_instrument_code": leg for leg in ("c1", "c2", "p1", "p2")},
    }
    client = MagicMock()

    def query(sql, parameters=None):
        if "option_order_book" in sql:
            prices = {"c1": (12, 13, 85955), "c2": (7, 8, 85959), "p1": (2, 3, 85958), "p2": (6, 7, 85959)}
            return SimpleNamespace(result_rows=[
                (code, event_time, 1, bid, 20, 2, ask, 20, 2)
                for code, (bid, ask, event_time) in prices.items()
            ])
        return SimpleNamespace(result_rows=[])

    client.query.side_effect = query
    with (
        patch("src.analytics.box_spread_engine.get_client", return_value=client),
        patch("src.analytics.box_spread_engine._run_row", return_value=stored),
        patch("src.analytics.box_spread_engine.update_run"),
        patch("src.analytics.box_spread_engine.insert_snapshots"),
        patch("src.analytics.box_spread_engine.insert_pricings") as pricings,
        patch("src.analytics.box_spread_engine.RunProgressReporter"),
    ):
        counts = process_run(stored["run_id"])
    rows = pricings.call_args.args[0]
    assert counts["snapshot_count"] == 2
    assert counts["pricing_count"] == 20
    assert {row["snapshot_time"] for row in rows} == set(aligned for aligned in [
        datetime(2026, 7, 1, 9, 0, tzinfo=TEHRAN),
        datetime(2026, 7, 1, 9, 0, 30, tzinfo=TEHRAN),
    ])
    assert all(row["classification"] == "ineligible_market_data" for row in rows)
    assert all(row["opportunity"] == 0 for row in rows)


def test_box_migrations_and_templates_are_discoverable():
    versions = _discover_versions()
    assert 14 in versions and 15 in versions
    from src.admin._render import _TEMPLATE_ENV
    for name in ("option/box_spread.html", "option/box_calculator.html", "option/box_spread_snapshots_list.html", "option/box_spread_pricings_list.html"):
        _TEMPLATE_ENV.get_template(name)


def test_box_calculator_request_and_four_ranked_routes():
    request = BoxCalculatorRequest(
        trade_date=date(2026, 7, 1), snapshot_time=time(9),
        underlying_instrument_code="stock", expiry_date=date(2026, 8, 1),
        lower_strike=100, upper_strike=110, direction="long", box_count=4,
        max_quote_age_seconds=120, max_cross_leg_skew_seconds=15,
    )
    assert request.box_count == 4
    assert request.max_quote_age_seconds == 120
    assert request.max_cross_leg_skew_seconds == 15
    snapshot = datetime(2026, 7, 1, 9, tzinfo=TEHRAN)
    routes = calculate_maker_routes(
        books={"c1": book(12, 13, 2, 2, 3), "c2": book(7, 8), "p1": book(2, 3), "p2": book(6, 7)},
        direction="long", lower_strike=100, upper_strike=110, box_count=4,
        multiplier=1000, buy_fee=.00103, sell_fee=.00103,
        settlement_cost_per_contract=None, tick_size=1, snapshot_at=snapshot,
        expiry_at=datetime(2026, 8, 1, 12, 30, tzinfo=TEHRAN),
        market_data_valid=True, quality_reasons=[],
    )
    assert len(routes) == 4
    assert [route["rank"] for route in routes] == [1, 2, 3, 4]
    assert all(route["profit_label"] == "pre_settlement_profit" for route in routes)
    assert all(route["monthly_metric"] == "monthly_equivalent_rate" for route in routes)
    c1_taker = next(route for route in routes if route["maker_leg"] != "c1")
    c1_leg = next(leg for leg in c1_taker["legs"] if leg["leg"] == "c1")
    assert c1_leg["slices"] == [
        {"level": 1, "price": 13.0, "quantity": 2},
        {"level": 2, "price": 14.0, "quantity": 2},
    ]
    assert routes[0]["expiry_profit"] is not None
    assert routes[0]["monthly_value"] is not None


def test_box_calculator_short_monthly_return_and_indicative_quality():
    snapshot = datetime(2026, 7, 1, 9, tzinfo=TEHRAN)
    routes = calculate_maker_routes(
        books={"c1": book(12, 13), "c2": book(7, 8), "p1": book(2, 3), "p2": book(6, 7)},
        direction="short", lower_strike=100, upper_strike=110, box_count=1,
        multiplier=1000, buy_fee=.00102, sell_fee=.00103,
        settlement_cost_per_contract=5, tick_size=1, snapshot_at=snapshot,
        expiry_at=datetime(2026, 8, 1, 12, 30, tzinfo=TEHRAN),
        market_data_valid=False, quality_reasons=["cross_leg_quote_skew"],
    )
    assert all(route["monthly_metric"] == "monthly_equivalent_rate" for route in routes)
    assert all(
        (route["monthly_value"] > 0) == (route["expiry_profit"] > 0)
        for route in routes
    )
    assert all(route["profit_label"] == "net_profit" for route in routes)
    assert all(not route["execution_grade"] for route in routes)
    assert all(route["quality_reasons"] == ["cross_leg_quote_skew"] for route in routes)


def test_box_calculator_route_and_postgres_migration_are_registered():
    from pathlib import Path
    from src.routes.box_spread import router

    assert "/api/v1/box-calculator/calculate" in {route.path for route in router.routes}
    migration = Path("alembic/versions/j0e1f2g3h4i5_option_fee_schedules.py").read_text()
    assert "option_fee_schedules" in migration
    assert "0.00103000" in migration and "0.00102000" in migration


def test_option_fee_lookup_requires_one_effective_market_schedule():
    from fastapi import HTTPException
    from src.routes.box_spread import _fee_market, _fee_schedule_for

    fee = SimpleNamespace(market="tse")

    class Session:
        def __init__(self, rows):
            self.rows = rows
            self.statement = None

        def execute(self, statement):
            self.statement = statement
            return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: self.rows))

    stock = SimpleNamespace(market_code=1)
    session = Session([fee])
    assert _fee_market(stock) == "tse"
    assert _fee_market(SimpleNamespace(market_code=2)) == "ifb"
    assert _fee_schedule_for(session, stock, date(2026, 7, 1)) is fee
    query = str(session.statement)
    assert "effective_from" in query and "effective_to IS NULL" in query
    for rows in ([], [fee, fee]):
        with pytest.raises(HTTPException, match="exactly one TSE"):
            _fee_schedule_for(Session(rows), stock, date(2026, 7, 1))
