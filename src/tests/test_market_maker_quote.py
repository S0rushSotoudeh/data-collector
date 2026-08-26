from datetime import date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

from src.analytics.depth import DepthBook, DepthLevel
from src.analytics.market_maker_quote import (
    Contract, EXPIRY_CUTOFF, HedgeLeg, MAX_BOOK_AGE_SECONDS,
    MAX_CROSS_LEG_SKEW_SECONDS, MONTHLY_RETURN_TARGET, MULTIPLIER, Route, TEHRAN,
    build_routes, main, monthly_growth, price_route, reconstruct_books,
    scan_market,
)


def book(at, bid, ask, bid_volume=20, ask_volume=20, level_two_volume=0):
    levels = [DepthLevel(1, bid, bid_volume, 1, ask, ask_volume, 1)]
    if level_two_volume:
        levels.append(DepthLevel(2, bid - 1, level_two_volume, 1, ask + 1, level_two_volume, 1))
    return DepthBook(at, tuple(levels))


def universe():
    return [
        Contract("C100", "call", 100), Contract("P100", "put", 100),
        Contract("C110", "call", 110), Contract("P110", "put", 110),
    ]


def test_route_enumeration_has_direct_parity_and_the_matching_box_direction():
    routes = build_routes(
        target=Contract("C100", "call", 100), contracts=universe(),
        underlying_code="STOCK", maker_side="sell",
    )
    assert [route.path for route in routes] == ["direct", "parity", "box:short:other_strike=110"]
    parity = routes[1]
    assert parity.terminal_cashflow == 100
    assert parity.hedge_legs == (
        HedgeLeg("P100", "buy", 1), HedgeLeg("STOCK", "buy", MULTIPLIER, "stock"),
    )
    box = routes[2]
    assert box.terminal_cashflow == -10
    assert {(leg.instrument_code, leg.side) for leg in box.hedge_legs} == {
        ("P100", "buy"), ("C110", "buy"), ("P110", "sell"),
    }


def test_illegal_parity_side_is_reported_without_hiding_box_routes():
    routes = build_routes(
        target=Contract("C100", "call", 100), contracts=universe(),
        underlying_code="STOCK", maker_side="buy",
    )
    assert routes[1].unavailable_reason == "not_allowed_for_call_buy"
    assert routes[2].path == "box:long:other_strike=110"


@pytest.mark.parametrize(("code", "side", "direction"), [
    ("C100", "buy", "long"), ("C100", "sell", "short"),
    ("C110", "buy", "short"), ("C110", "sell", "long"),
    ("P100", "buy", "short"), ("P100", "sell", "long"),
    ("P110", "buy", "long"), ("P110", "sell", "short"),
])
def test_every_target_leg_and_side_selects_the_correct_box_direction(code, side, direction):
    target = next(contract for contract in universe() if contract.instrument_code == code)
    routes = build_routes(
        target=target, contracts=universe(), underlying_code="STOCK", maker_side=side,
    )
    box = next(route for route in routes if route.path.startswith("box:"))
    assert box.path.startswith(f"box:{direction}:")
    assert all(leg.instrument_code != target.instrument_code for leg in box.hedge_legs)
    assert len(box.hedge_legs) == 3


def test_reconstruct_books_carries_each_level_and_uses_latest_level_one_time():
    at = datetime(2026, 8, 12, 9, 1, tzinfo=TEHRAN)
    rows = [
        ("C", 85950, 2, 9, 4, 1, 12, 5, 1),
        ("C", 85958, 1, 10, 2, 1, 11, 3, 1),
        ("C", 90015, 2, 8, 7, 1, 13, 8, 1),
    ]
    rebuilt = reconstruct_books(rows, at)["C"]
    assert rebuilt.source_time.time().isoformat() == "08:59:58"
    assert [level.level for level in rebuilt.levels] == [1, 2]
    assert rebuilt.levels[1].ask_price == 13


def test_parity_price_and_capacity_use_only_top_of_book():
    at = datetime(2026, 8, 12, 10, 0, tzinfo=TEHRAN)
    expiry = datetime.combine(date(2026, 8, 13), EXPIRY_CUTOFF, TEHRAN)
    route = Route("parity", 100, (
        HedgeLeg("P100", "buy", 1), HedgeLeg("STOCK", "buy", MULTIPLIER, "stock"),
    ))
    books = {
        "C100": book(at, 19, 22, 50, 50),
        "P100": book(at, 9, 10, 30, 10, 10),
        "STOCK": book(at, 109, 110, 50_000, 10_000, 5_000),
    }
    priced = price_route(
        route=route, target=Contract("C100", "call", 100), maker_side="sell",
        books=books, at=at, expiry_at=expiry,
    )
    assert priced["max_quantity"] == 10
    assert priced["price"] == 21
    assert priced["best_bid"] == 19
    assert priced["best_ask"] == 22
    assert priced["price_minus_best_bid"] == 2
    assert priced["price_minus_best_ask"] == -1
    assert priced["maker_side_distance"] == 1
    assert priced["reason"] is None


def test_put_buy_parity_returns_the_highest_valid_passive_bid():
    at = datetime(2026, 8, 12, 10, 0, tzinfo=TEHRAN)
    route = Route("parity", 100, (
        HedgeLeg("C100", "sell", 1), HedgeLeg("STOCK", "buy", MULTIPLIER, "stock"),
    ))
    books = {
        "P100": book(at, 9, 12, 50, 50),
        "C100": book(at, 30, 31, 20, 20),
        "STOCK": book(at, 69, 70, 20_000, 20_000),
    }
    priced = price_route(
        route=route, target=Contract("P100", "put", 100), maker_side="buy",
        books=books, at=at, expiry_at=at + timedelta(days=30),
    )
    assert priced["max_quantity"] == 20
    assert priced["price"] == 56
    assert priced["best_bid"] == 9
    assert priced["best_ask"] == 12
    assert priced["price_minus_best_bid"] == 47
    assert priced["price_minus_best_ask"] == 44
    assert priced["maker_side_distance"] == 47
    assert priced["reason"] is None


def test_box_price_is_calculated_from_three_taker_legs_then_compared_to_market():
    at = datetime(2026, 8, 12, 10, 0, tzinfo=TEHRAN)
    route = Route("box:long:other_strike=110", 10, (
        HedgeLeg("C110", "sell", 1),
        HedgeLeg("P100", "sell", 1),
        HedgeLeg("P110", "buy", 1),
    ))
    books = {
        "C100": book(at, 1, 2),
        "C110": book(at, 5, 6),
        "P100": book(at, 2, 3),
        "P110": book(at, 5, 6),
    }
    priced = price_route(
        route=route, target=Contract("C100", "call", 100), maker_side="buy",
        books=books, at=at, expiry_at=at + timedelta(days=30),
    )
    assert priced["max_quantity"] == 20
    assert priced["price"] == 10
    assert priced["best_bid"] == 1
    assert priced["best_ask"] == 2
    assert priced["price_minus_best_bid"] == 9
    assert priced["price_minus_best_ask"] == 8
    assert priced["maker_side_distance"] == 9
    assert priced["reason"] is None


def test_calculated_price_is_returned_even_when_it_is_behind_the_current_market():
    at = datetime(2026, 8, 12, 10, 0, tzinfo=TEHRAN)
    route = Route("direct", 0, (HedgeLeg("C100", "sell", 1),))
    priced = price_route(
        route=route, target=Contract("C100", "call", 100), maker_side="buy",
        books={"C100": book(at, 100, 110, 12, 15)}, at=at,
        expiry_at=at + timedelta(days=30),
    )
    assert priced["path"] == "direct"
    assert priced["price"] == 99
    assert priced["max_quantity"] == 12
    assert priced["best_bid"] == 100
    assert priced["best_ask"] == 110
    assert priced["price_minus_best_bid"] == -1
    assert priced["price_minus_best_ask"] == -11
    assert priced["maker_side_distance"] == -1
    assert priced["reason"] is None


def test_direct_price_and_capacity_ignore_deeper_levels():
    at = datetime(2026, 8, 12, 10, 0, tzinfo=TEHRAN)
    route = Route("direct", 0, (HedgeLeg("C100", "buy", 1),))
    priced = price_route(
        route=route, target=Contract("C100", "call", 100), maker_side="sell",
        books={"C100": book(at, 7_000, 7_500, 17, 3, 100)}, at=at,
        expiry_at=at + timedelta(days=30),
    )
    assert priced["price"] == 7_516
    assert priced["max_quantity"] == 3
    assert priced["best_ask"] == 7_500


def test_calculated_boundary_and_non_crossing_passive_price_are_both_reported():
    at = datetime(2026, 8, 12, 10, 0, tzinfo=TEHRAN)
    priced = price_route(
        route=Route("test", 100, (HedgeLeg("H", "sell", 1),)),
        target=Contract("T", "put", 100), maker_side="buy",
        books={"T": book(at, 20, 23), "H": book(at, 90, 91)}, at=at,
        expiry_at=at + timedelta(days=30),
    )
    assert priced["price"] > priced["best_ask"]
    assert priced["suggested_passive_price"] == 22
    assert priced["suggested_passive_distance"] == 2
    assert priced["crosses_opposite_quote"] is True
    assert priced["profit_headroom_at_passive_price"] == priced["price"] - 22
    assert priced["action"] == "immediate"
    assert priced["execution_price"] == 23
    assert priced["profit_headroom_at_execution"] == priced["price"] - 23


def test_stale_or_skewed_books_are_rejected():
    at = datetime(2026, 8, 12, 10, 0, tzinfo=TEHRAN)
    route = Route("test", 100, (HedgeLeg("P", "buy", 1),))
    stale = price_route(
        route=route, target=Contract("C", "call", 100), maker_side="sell",
        books={
            "C": book(at, 10, 11),
            "P": book(at - timedelta(seconds=MAX_BOOK_AGE_SECONDS + 1), 2, 3),
        },
        at=at, expiry_at=at + timedelta(days=30),
    )
    assert stale["reason"] == "stale_book:P"
    skewed = price_route(
        route=route, target=Contract("C", "call", 100), maker_side="sell",
        books={
            "C": book(at, 10, 11),
            "P": book(at - timedelta(seconds=MAX_CROSS_LEG_SKEW_SECONDS + 1), 2, 3),
        },
        at=at, expiry_at=at + timedelta(days=30),
    )
    assert skewed["reason"] == "cross_leg_quote_skew"


def test_scan_quality_can_reject_wide_books():
    at = datetime(2026, 8, 12, 10, 0, tzinfo=TEHRAN)
    priced = price_route(
        route=Route("direct", 0, (HedgeLeg("C", "buy", 1),)),
        target=Contract("C", "call", 100), maker_side="sell",
        books={"C": book(at, 1, 100)}, at=at,
        expiry_at=at + timedelta(days=30), max_spread_percent=20,
    )
    assert priced["reason"] == "wide_book:C"


def test_monthly_hurdle_matches_one_and_two_month_examples():
    at = datetime(2026, 1, 1, tzinfo=TEHRAN)
    month = timedelta(seconds=(365.25 / 12) * 24 * 60 * 60)
    assert monthly_growth(at, at + month) == pytest.approx(1 + MONTHLY_RETURN_TARGET)
    assert monthly_growth(at, at + 2 * month) == pytest.approx((1 + MONTHLY_RETURN_TARGET) ** 2)


def test_cli_emits_json_and_returns_nonzero_json_error(capsys):
    output = {"at": "x", "option_instrument_code": "C", "side": "buy", "paths": []}
    with patch("src.analytics.market_maker_quote.quote_paths", return_value=output):
        assert main(["2026-08-12T10:30:00", "C", "buy"]) == 0
    assert '"option_instrument_code": "C"' in capsys.readouterr().out

    assert main(["not-a-time", "C", "buy"]) == 1
    assert "time must be an ISO datetime" in capsys.readouterr().err

    with patch("src.analytics.market_maker_quote.quote_paths", side_effect=RuntimeError("database down")):
        assert main(["2026-08-12T10:30:00", "C", "buy"]) == 1
    assert '"error": "pricing failed: database down"' in capsys.readouterr().err


def test_market_scan_ranks_percentage_distance_and_can_filter_direct_routes():
    at = datetime(2026, 8, 12, 10, 0, tzinfo=TEHRAN)
    call = SimpleNamespace(
        instrument_code="C100", option_type="call", strike_price=100,
        expiry_date=date(2026, 9, 12), underlying_instrument_code="STOCK",
        listing_date=date(2026, 1, 1), symbol="CALL",
    )
    put = SimpleNamespace(
        instrument_code="P100", option_type="put", strike_price=100,
        expiry_date=date(2026, 9, 12), underlying_instrument_code="STOCK",
        listing_date=date(2026, 1, 1), symbol="PUT",
    )
    scalar_rows = SimpleNamespace(all=lambda: [call, put])
    stock_rows = SimpleNamespace(all=lambda: ["STOCK"])
    session = MagicMock()
    session.execute.side_effect = [
        SimpleNamespace(scalars=lambda: scalar_rows),
        SimpleNamespace(scalars=lambda: stock_rows),
    ]
    session.__enter__.return_value = session
    books = {
        "C100": book(at, 20, 22, 10, 10),
        "P100": book(at, 8, 10, 10, 10),
        "STOCK": book(at, 108, 110, 20_000, 20_000),
    }
    with (
        patch("src.analytics.market_maker_quote.SessionLocal", return_value=session),
        patch("src.analytics.market_maker_quote.get_client", return_value=object()),
        patch("src.analytics.market_maker_quote._query_depth_rows", side_effect=[[], []]),
        patch("src.analytics.market_maker_quote.reconstruct_books", return_value=books),
    ):
        result = scan_market(at, ("sell",), limit=10, exclude_direct=True)
    assert result["targets_scanned"] == 2
    assert all(item["path"] != "direct" for item in result["results"])
    distances = [item["maker_side_distance_percent"] for item in result["results"]]
    assert distances == sorted(distances, reverse=True)


def test_cli_all_both_dispatches_to_market_scan(capsys):
    output = {"at": "x", "results": []}
    with patch("src.analytics.market_maker_quote.scan_market", return_value=output) as scan:
        assert main([
            "2026-08-12T10:30:00", "all", "both", "--limit", "7",
            "--competitive-only", "--exclude-direct",
        ]) == 0
    scan.assert_called_once()
    assert '"results": []' in capsys.readouterr().out
