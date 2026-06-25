import math
from datetime import date

import numpy as np
import pytest

from src.analytics.engine import _hhmmss_to_seconds, _seconds_to_hhmmss
from src.analytics.yield_curve import (
    FACE_VALUE,
    _failed_fit,
    classify_signal,
    fit_nelson_siegel,
    ns_yield,
    yield_from_price,
)

# ── ns_yield ──────────────────────────────────────────────────────


class TestNsYield:
    def test_at_t_zero_equals_b0_plus_b1(self):
        assert ns_yield(0.0, 0.3, -0.05, 0.1, 2.0) == 0.25

    def test_at_t_zero_with_negative_b1(self):
        assert ns_yield(0.0, 0.4, -0.1, 0.05, 1.5) == pytest.approx(0.3, rel=1e-12)

    def test_asymptote_to_b0_for_large_t(self):
        b0, b1, b2, lam = 0.3, -0.05, 0.1, 2.0
        result = ns_yield(1e6, b0, b1, b2, lam)
        assert result == pytest.approx(b0, abs=1e-6)

    def test_monotonic_increasing_with_b1_negative(self):
        t1, t2 = 0.5, 3.0
        y1 = ns_yield(t1, 0.3, -0.15, 0.05, 2.0)
        y2 = ns_yield(t2, 0.3, -0.15, 0.05, 2.0)
        assert y2 > y1

    def test_symmetry_small_t(self):
        y = ns_yield(1e-10, 0.3, -0.05, 0.1, 2.0)
        assert abs(y - 0.25) < 1e-6

    def test_negative_t_returns_b0_plus_b1(self):
        assert ns_yield(-1.0, 0.5, -0.2, 0.1, 2.0) == 0.3

    def test_lambda_scale_invariance(self):
        t = 1.0
        y1 = ns_yield(t, 0.3, -0.05, 0.1, 1.0)
        y2 = ns_yield(t * 2, 0.3, -0.05, 0.1, 2.0)
        assert abs(y1 - y2) < 1e-10

    def test_b2_effect_vanishes_at_infinity(self):
        b0, b1, lam = 0.3, -0.05, 2.0
        y_high_b2 = ns_yield(1e6, b0, b1, 1.0, lam)
        y_low_b2 = ns_yield(1e6, b0, b1, -1.0, lam)
        assert abs(y_high_b2 - y_low_b2) < 5e-6


# ── yield_from_price ──────────────────────────────────────────────


class TestYieldFromPrice:
    def test_par_bond_yields_zero(self):
        y = yield_from_price(FACE_VALUE, FACE_VALUE, 1.0)
        assert y == 0.0

    def test_discount_bond_positive_yield(self):
        y = yield_from_price(900000, FACE_VALUE, 1.0)
        expected = math.log(FACE_VALUE / 900000) / 1.0
        assert y == pytest.approx(expected, rel=1e-12)

    def test_premium_bond_negative_yield(self):
        y = yield_from_price(1_100_000, FACE_VALUE, 1.0)
        assert y < 0

    def test_short_ttm_amplifies_yield(self):
        y_short = yield_from_price(950000, FACE_VALUE, 0.25)
        y_long = yield_from_price(950000, FACE_VALUE, 1.0)
        assert abs(y_short) > abs(y_long)

    def test_zero_price_returns_nan(self):
        assert math.isnan(yield_from_price(0, FACE_VALUE, 1.0))

    def test_negative_price_returns_nan(self):
        assert math.isnan(yield_from_price(-100, FACE_VALUE, 1.0))

    def test_zero_ttm_returns_nan(self):
        assert math.isnan(yield_from_price(900000, FACE_VALUE, 0.0))

    def test_negative_ttm_returns_nan(self):
        assert math.isnan(yield_from_price(900000, FACE_VALUE, -1.0))

    def test_roundtrip_price_yield_price(self):
        price = 847190
        ttm = 0.6132785763175906
        y = yield_from_price(price, FACE_VALUE, ttm)
        recovered = FACE_VALUE * math.exp(-y * ttm)
        assert recovered == pytest.approx(price, rel=1e-10)


# ── fit_nelson_siegel ─────────────────────────────────────────────


class TestFitNelsonSiegel:
    def test_fewer_than_4_bonds_returns_failed(self):
        result = fit_nelson_siegel([0.1, 0.2, 0.3], [1.0, 2.0, 3.0])
        assert result["converged"] == 0
        assert "Need at least 4 bonds" in result["error_message"]

    def test_exactly_4_bonds_converges(self):
        yields = [0.25, 0.23, 0.21, 0.20]
        ttms = [0.5, 1.0, 2.0, 5.0]
        result = fit_nelson_siegel(yields, ttms)
        assert result["converged"] == 1
        assert result["rmse"] < 0.1

    def test_recovers_known_ns_params(self):
        b0, b1, b2, lam = 0.25, -0.05, 0.08, 2.5
        ttms = [0.25, 0.5, 1.0, 2.0, 3.0, 5.0, 7.0, 10.0]
        yields = [ns_yield(t, b0, b1, b2, lam) for t in ttms]
        result = fit_nelson_siegel(yields, ttms)
        assert result["converged"] == 1
        assert result["beta0"] == pytest.approx(b0, abs=0.05)
        assert result["beta1"] == pytest.approx(b1, abs=0.05)
        assert result["beta2"] == pytest.approx(b2, abs=0.05)
        assert result["lambda"] == pytest.approx(lam, abs=0.5)
        assert result["rmse"] < 1e-10

    def test_recovers_nearly_flat_curve(self):
        ttms = [0.5, 1.0, 2.0, 5.0, 10.0]
        yields = [0.22, 0.21, 0.20, 0.195, 0.19]
        result = fit_nelson_siegel(yields, ttms)
        assert result["converged"] == 1
        assert result["rmse"] < 0.02

    def test_upward_sloping_curve(self):
        ttms = [0.5, 1.0, 2.0, 5.0, 10.0]
        yields = [0.15, 0.18, 0.22, 0.28, 0.30]
        result = fit_nelson_siegel(yields, ttms)
        assert result["converged"] == 1
        assert result["beta0"] > 0.28
        assert result["beta1"] < 0

    def test_downward_sloping_curve(self):
        ttms = [0.5, 1.0, 2.0, 5.0, 10.0]
        yields = [0.30, 0.28, 0.25, 0.22, 0.20]
        result = fit_nelson_siegel(yields, ttms)
        assert result["converged"] == 1
        assert result["beta0"] < 0.25

    def test_all_identical_yields(self):
        ttms = [0.5, 1.0, 2.0, 5.0]
        yields = [0.20, 0.20, 0.20, 0.20]
        result = fit_nelson_siegel(yields, ttms)
        assert result["converged"] == 1
        assert result["beta0"] == pytest.approx(0.20, abs=0.01)
        assert result["rmse"] < 1e-8

    def test_fitted_yields_are_close_to_input(self):
        ttms = [0.25, 0.5, 1.0, 2.0, 3.0, 5.0, 7.0, 10.0]
        yields = [0.28, 0.26, 0.24, 0.22, 0.21, 0.20, 0.195, 0.19]
        result = fit_nelson_siegel(yields, ttms)
        assert result["converged"] == 1
        b0, b1, b2, lam = result["beta0"], result["beta1"], result["beta2"], result["lambda"]
        for t, y in zip(ttms, yields):
            fitted = ns_yield(t, b0, b1, b2, lam)
            assert abs(fitted - y) < 0.05

    def test_params_within_bounds(self):
        yields = [0.35, 0.30, 0.25, 0.22, 0.20, 0.18]
        ttms = [0.25, 0.5, 1.0, 2.0, 5.0, 10.0]
        result = fit_nelson_siegel(yields, ttms)
        assert result["converged"] == 1
        assert 0 <= result["beta0"] <= 1
        assert -1 <= result["beta1"] <= 1
        assert -1 <= result["beta2"] <= 1
        assert 0.01 <= result["lambda"] <= 10

    def test_stress_discount_bonds(self):
        ttms = [0.1, 0.5, 0.8, 1.0, 2.0]
        price = 850000
        yields = [yield_from_price(price, FACE_VALUE, t) for t in ttms]
        result = fit_nelson_siegel(yields, ttms)
        assert result["converged"] == 1

    def test_stress_mixed_discount_premium(self):
        ttms = [0.25, 0.5, 1.0, 2.0, 3.0, 5.0]
        prices = [980000, 950000, 920000, 880000, 860000, 840000]
        yields = [yield_from_price(p, FACE_VALUE, t) for p, t in zip(prices, ttms)]
        result = fit_nelson_siegel(yields, ttms)
        assert result["converged"] == 1

    def test_humped_curve(self):
        ttms = [0.5, 1.0, 2.0, 3.0, 5.0, 10.0]
        yields = [0.20, 0.24, 0.28, 0.27, 0.25, 0.23]
        result = fit_nelson_siegel(yields, ttms)
        assert result["converged"] == 1
        assert result["rmse"] < 0.02


# ── classify_signal ──────────────────────────────────────────────


class TestClassifySignal:
    def test_above_threshold_is_cheap(self):
        assert classify_signal(100.0, 50.0) == "cheap"

    def test_at_threshold_positive_is_fair(self):
        assert classify_signal(50.0, 50.0) == "fair"

    def test_below_negative_threshold_is_rich(self):
        assert classify_signal(-100.0, 50.0) == "rich"

    def test_at_threshold_negative_is_fair(self):
        assert classify_signal(-50.0, 50.0) == "fair"

    def test_within_threshold_is_fair(self):
        assert classify_signal(10.0, 50.0) == "fair"

    def test_zero_spread_is_fair(self):
        assert classify_signal(0.0, 50.0) == "fair"

    def test_just_above_threshold_is_cheap(self):
        assert classify_signal(50.001, 50.0) == "cheap"

    def test_just_below_negative_threshold_is_rich(self):
        assert classify_signal(-50.001, 50.0) == "rich"

    def test_custom_threshold(self):
        assert classify_signal(30.0, 25.0) == "cheap"
        assert classify_signal(20.0, 25.0) == "fair"

    def test_zero_threshold_never_fair(self):
        assert classify_signal(1.0, 0.0) == "cheap"
        assert classify_signal(-1.0, 0.0) == "rich"


# ── _failed_fit ──────────────────────────────────────────────────


class TestFailedFit:
    def test_returns_expected_structure(self):
        result = _failed_fit("test error")
        assert result == {
            "beta0": None,
            "beta1": None,
            "beta2": None,
            "lambda": None,
            "rmse": None,
            "converged": 0,
            "error_message": "test error",
        }

    def test_converts_to_string(self):
        result = _failed_fit(42)
        assert result["error_message"] == "42"


# ── Engine helpers ────────────────────────────────────────────────


class TestHhmmssConversions:
    def test_midnight(self):
        assert _hhmmss_to_seconds(0) == 0
        assert _seconds_to_hhmmss(0) == 0

    def test_market_open_083000(self):
        assert _hhmmss_to_seconds(83000) == 8 * 3600 + 30 * 60

    def test_market_close_150000(self):
        assert _hhmmss_to_seconds(150000) == 15 * 3600

    def test_roundtrip_various_times(self):
        times = [0, 1, 83000, 93000, 120000, 145930, 150000, 235959]
        for t in times:
            assert _seconds_to_hhmmss(_hhmmss_to_seconds(t)) == t

    def test_seconds_boundary(self):
        assert _hhmmss_to_seconds(10000) == 3600
        assert _hhmmss_to_seconds(10030) == 3630

    def test_bucket_floor(self):
        seconds = _hhmmss_to_seconds(100015)
        floored = (seconds // 30) * 30
        assert floored == 36000
        assert _seconds_to_hhmmss(floored) == 100000

    def test_bucket_ceil(self):
        seconds = _hhmmss_to_seconds(100045)
        floored = (seconds // 30) * 30
        assert floored == 36030
        assert _seconds_to_hhmmss(floored) == 100030


# ── FACE_VALUE constant ──────────────────────────────────────────


class TestConstants:
    def test_face_value_is_one_million_irr(self):
        assert FACE_VALUE == 1_000_000
