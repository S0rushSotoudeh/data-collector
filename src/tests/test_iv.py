import math

import pytest
from pydantic import ValidationError

from src.analytics.iv import (
    WingParameters, black76_price, fit_orc_wing, implied_volatility,
    interpolate_parameters, orc_wing, parity_forward_bounds, robust_forward,
)
from src.analytics.iv_config import IVSurfaceRunConfig


def test_black76_round_trip_call_and_put():
    for option_type in ("call", "put"):
        price = black76_price(100, 105, 0.2, 0.5, 0.37, option_type)
        assert implied_volatility(price, 100, 105, 0.2, 0.5, option_type) == pytest.approx(0.37, abs=1e-10)


def test_iv_rejects_arbitrage_violation():
    with pytest.raises(ValueError, match="no_arbitrage"):
        implied_volatility(101, 100, 100, 0, 1, "call")


def test_parity_forward_executable_interval():
    lower, upper = parity_forward_bounds(100, 0.1, 0.5, 8, 10, 7, 9)
    growth = math.exp(0.05)
    assert lower == pytest.approx(100 + growth * (8 - 9))
    assert upper == pytest.approx(100 + growth * (10 - 7))
    lo, hi, central = robust_forward([(lower, upper, 1), (100, 102, 10)])
    assert lo == lower and hi == upper
    assert 100 <= central <= 102


def test_orc_wing_is_continuous_at_all_boundaries():
    p = WingParameters(0.3, -0.15, 0.8, 0.6, -0.25, 0.2)
    for boundary in (p.dc * (1 + p.dsm), p.dc, 0, p.uc, p.uc * (1 + p.usm)):
        assert orc_wing(boundary - 1e-9, p) == pytest.approx(orc_wing(boundary + 1e-9, p), abs=1e-8)


def test_documented_orc_interpolation_example():
    # Manual example: 30 DTE between the 10/50-day skews gives vc=21.5%,
    # sc=-0.75, cc=0.75 and ln(110/105) ~= 0.05, producing about 21.4% IV.
    p = WingParameters(.215, -.0075, .015, .0075, -.5, .5)
    value = orc_wing(math.log(110 / 105), p)
    assert value * 100 == pytest.approx(21.47, abs=.08)


def test_fit_recovers_synthetic_smile():
    expected = WingParameters(0.28, -0.12, 0.7, 0.5, -0.25, 0.22)
    x = [-.6, -.4, -.25, -.15, -.05, .05, .12, .22, .35, .55]
    y = [orc_wing(value, expected) for value in x]
    actual, rmse, converged = fit_orc_wing(x, y)
    assert converged
    assert rmse < 1e-6
    assert actual.vc == pytest.approx(expected.vc, abs=1e-4)
    assert actual.sc == pytest.approx(expected.sc, abs=1e-4)


def test_sparse_fit_rejected():
    with pytest.raises(ValueError, match="insufficient_strikes"):
        fit_orc_wing([-.2, -.1, .1, .2], [.3, .2, .2, .3])


def test_maturity_interpolation():
    left = WingParameters(.2, -.1, .5, .6, -.2, .2)
    right = WingParameters(.4, .1, .9, 1.0, -.4, .4)
    middle = interpolate_parameters(left, right, .1, .3, .2)
    assert middle.vc == pytest.approx(.3)
    assert middle.pc == pytest.approx(.7)


@pytest.mark.parametrize("value", [None, 0, 9, 10.5, 20, 31, 3600])
def test_iv_run_rejects_missing_or_unsupported_intervals(value):
    payload = {
        "underlying_instrument_code": "1", "start_date": "2026-01-01", "end_date": "2026-01-01",
        "pricing_convention_id": "00000000-0000-0000-0000-000000000001",
        "interval_seconds": value,
    }
    if value is None:
        payload.pop("interval_seconds")
    with pytest.raises(ValidationError):
        IVSurfaceRunConfig.model_validate(payload)


@pytest.mark.parametrize("value", [10, 30])
def test_iv_run_accepts_only_supported_intervals(value):
    config = IVSurfaceRunConfig.model_validate({
        "underlying_instrument_code": "1", "start_date": "2026-01-01", "end_date": "2026-01-01",
        "pricing_convention_id": "00000000-0000-0000-0000-000000000001", "interval_seconds": value,
    })
    assert config.interval_seconds == value
