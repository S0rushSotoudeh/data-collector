from datetime import date

import pytest

from src.routes.yield_spread import _aggregate_daily, _box_stats, _quantile


class TestQuantile:
    def test_single_value(self) -> None:
        assert _quantile([5.0], 0.5) == 5.0

    def test_median_even(self) -> None:
        assert _quantile([1.0, 2.0, 3.0, 4.0], 0.5) == 2.5

    def test_median_odd(self) -> None:
        assert _quantile([1.0, 2.0, 3.0], 0.5) == 2.0

    def test_q1(self) -> None:
        assert _quantile([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0], 0.25) == 2.75

    def test_extremes(self) -> None:
        assert _quantile([10.0, 20.0], 0.0) == 10.0
        assert _quantile([10.0, 20.0], 1.0) == 20.0

    def test_empty(self) -> None:
        import math
        assert math.isnan(_quantile([], 0.5))


class TestBoxStats:
    def test_basic(self) -> None:
        stats = _box_stats([1.0, 2.0, 3.0, 4.0, 5.0])
        assert stats["n"] == 5
        assert stats["mean"] == pytest.approx(3.0)
        assert stats["box"] == [1.0, 2.0, 3.0, 4.0, 5.0]
        assert stats["outliers"] == []

    def test_outliers(self) -> None:
        # 1..10 plus an extreme outlier at 100
        stats = _box_stats([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0, 100.0])
        assert stats["n"] == 11
        assert 100.0 in stats["outliers"]
        assert stats["box"][0] == 1.0
        assert stats["box"][4] == 10.0

    def test_filters_none_and_nan(self) -> None:
        stats = _box_stats([None, 2.0, float("nan"), 4.0])
        assert stats["n"] == 2
        assert stats["box"] == [2.0, 2.5, 3.0, 3.5, 4.0]
        assert stats["outliers"] == []

    def test_empty(self) -> None:
        stats = _box_stats([])
        assert stats["n"] == 0
        assert stats["box"] is None
        assert stats["outliers"] == []


class TestAggregateDaily:
    def test_groups_by_date_side(self) -> None:
        points = [
            {"trade_date": date(2026, 6, 16), "curve_side": "bid", "spread_bps": 10.0},
            {"trade_date": date(2026, 6, 16), "curve_side": "bid", "spread_bps": 20.0},
            {"trade_date": date(2026, 6, 16), "curve_side": "ask", "spread_bps": 5.0},
            {"trade_date": date(2026, 6, 17), "curve_side": "bid", "spread_bps": 12.0},
        ]
        days = _aggregate_daily(points)
        assert len(days) == 3
        bid_first = [d for d in days if d["curve_side"] == "bid" and d["trade_date"] == date(2026, 6, 16)][0]
        assert bid_first["n"] == 2
        assert bid_first["box"] == [10.0, 12.5, 15.0, 17.5, 20.0]
        assert bid_first["mean"] == pytest.approx(15.0)

    def test_preserves_first_seen_order(self) -> None:
        points = [
            {"trade_date": date(2026, 6, 17), "curve_side": "bid", "spread_bps": 1.0},
            {"trade_date": date(2026, 6, 16), "curve_side": "bid", "spread_bps": 2.0},
        ]
        days = _aggregate_daily(points)
        assert days[0]["trade_date"] == date(2026, 6, 17)
        assert days[1]["trade_date"] == date(2026, 6, 16)

    def test_empty(self) -> None:
        assert _aggregate_daily([]) == []
