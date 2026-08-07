import math
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from src.admin._render import _TEMPLATE_ENV
from src.analytics.iv import WingParameters, fit_orc_wing_robust, orc_wing
from src.analytics.mispricing_config import OptionMispricingRunConfig
from src.analytics.mispricing_engine import _observation, _quote, _ranking_rows
from src.analytics.mispricing_universe import discover_option_universe
from src.db.clickhouse.mispricing import get_observations

TEHRAN = ZoneInfo("Asia/Tehran")
CONVENTION = "00000000-0000-0000-0000-000000000001"


def _config(**overrides):
    payload = {"trade_date": "2026-07-08", "pricing_convention_id": CONVENTION} | overrides
    return OptionMispricingRunConfig.model_validate(payload)


def test_mispricing_config_defaults_and_single_date_session_validation():
    config = _config()
    assert config.interval_seconds == 30
    assert config.max_quote_age_seconds == 60
    with pytest.raises(ValidationError, match="start_time"):
        _config(start_time="12:31:00", end_time="12:30:00")


def test_robust_wing_rejects_an_isolated_midpoint_iv_outlier():
    expected = WingParameters(.28, -.12, .7, .5, -.3, .25)
    x = [-.45, -.32, -.22, -.12, -.04, .05, .12, .22, .35, .48]
    y = [orc_wing(value, expected) for value in x]
    y[7] += .55

    fit = fit_orc_wing_robust(x, y)

    assert fit.converged
    assert 7 in fit.excluded_indices
    assert len(fit.kept_indices) == 9
    assert fit.rmse < .01


def test_robust_wing_fails_when_rejection_would_leave_insufficient_coverage():
    x = [-.3, -.2, -.1, -.05, .05, .1, .2]
    y = [.3, .28, .26, .25, .25, .27, 1.2]
    with pytest.raises(ValueError, match="insufficient_strikes_after_outlier_rejection"):
        fit_orc_wing_robust(x, y)


@pytest.mark.parametrize(
    ("raw", "reason"),
    [
        (None, "missing_quote"),
        ((83045, 0, 10, 1, 1), "one_sided_quote"),
        ((83045, 11, 10, 1, 1), "crossed_quote"),
        ((82900, 9, 10, 1, 1), "stale_quote"),
    ],
)
def test_quote_rejections_match_replay_quality_rules(raw, reason):
    snapshot = datetime(2026, 7, 8, 8, 31, tzinfo=TEHRAN)
    assert _quote(raw, snapshot, 30)["rejection"] == reason


def test_contract_has_one_fair_value_and_signed_bid_ask_midpoint_distances():
    snapshot = datetime(2026, 7, 8, 9, 0, tzinfo=TEHRAN)
    params = WingParameters(.3, 0, .2, .2, -.3, .3)
    fit = {
        "forward": 100.0, "rate": .1, "rate_source": "bond_curve", "ttm_years": .5,
        "rmse": .001, "quality_status": "valid",
    }
    contract = {
        "underlying_instrument_code": "U", "instrument_code": "C100", "option_type": "call",
        "strike": 100.0, "expiry_date": date(2027, 1, 1),
    }
    quote = {"raw": (90000, 7.0, 9.0, 12, 10), "quote_time": snapshot, "age": 0, "rejection": ""}

    row = _observation(
        run_id=CONVENTION, snapshot=snapshot, contract=contract, quote=quote, fit=fit,
        fit_state={"parameters": params, "excluded_codes": set()}, price_factor=1.0, now=snapshot,
    )

    assert row["fair_price"] is not None
    assert row["bid_distance"] == pytest.approx(7 - row["fair_price"])
    assert row["ask_distance"] == pytest.approx(9 - row["fair_price"])
    assert row["midpoint_distance"] == pytest.approx(8 - row["fair_price"])
    assert row["bid_distance_bps"] == pytest.approx(row["bid_distance"] / row["fair_price"] * 10_000)
    assert row["ask_distance_bps"] == pytest.approx(row["ask_distance"] / row["fair_price"] * 10_000)


def test_invalid_quote_keeps_price_diagnostics_but_is_not_mispricing():
    snapshot = datetime(2026, 7, 8, 9, 0, tzinfo=TEHRAN)
    contract = {
        "underlying_instrument_code": "U", "instrument_code": "C100", "option_type": "call",
        "strike": 100.0, "expiry_date": date(2027, 1, 1),
    }
    fit = {
        "forward": 100.0, "rate": .1, "rate_source": "bond_curve", "ttm_years": .5,
        "rmse": .001, "quality_status": "valid",
    }
    row = _observation(
        run_id=CONVENTION, snapshot=snapshot, contract=contract,
        quote={"raw": (83000, 7.0, 9.0, 12, 10), "quote_time": snapshot, "age": 90, "rejection": "stale_quote"},
        fit=fit, fit_state={"parameters": WingParameters(.3, 0, .2, .2, -.3, .3), "excluded_codes": set()},
        price_factor=1.0, now=snapshot,
    )
    assert row["quality_status"] == "invalid"
    assert row["bid_price"] == 7.0 and row["fair_price"] is not None and row["ask_price"] == 9.0
    assert row["bid_distance"] is None and row["midpoint_distance_bps"] is None


def test_ranking_uses_p90_absolute_midpoint_and_threshold_counts():
    snapshots = [datetime(2026, 7, 8, 9, i, tzinfo=TEHRAN) for i in range(2)]
    stats = {
        "U": {
            "midpoint": [-10.0, 30.0, -60.0, 120.0], "bid": [-20.0, 35.0], "ask": [15.0, -150.0],
            "contracts": {"A", "B"}, "expiries": {date(2027, 1, 1)}, "snapshots": set(snapshots),
            "affected_contracts": {"A", "B"}, "excluded": 3, "warnings": {"reference_outliers_excluded"},
        }
    }
    rows = _ranking_rows(CONVENTION, date(2026, 7, 8), {"U"}, snapshots, stats, {"U": set()}, snapshots[0])
    row = rows[0]
    assert row["p90_abs_midpoint_bps"] == pytest.approx(102)
    assert row["outside_25_count"] == 3
    assert row["outside_50_count"] == 2
    assert row["outside_100_count"] == 1
    assert row["largest_ask_deviation_bps"] == -150
    assert row["snapshot_coverage"] == 1


async def test_universe_is_driven_by_historical_quotes_not_current_status(monkeypatch):
    quote_result = SimpleNamespace(result_rows=[])
    instruments = []
    for index in range(7):
        for option_type in ("call", "put"):
            code = f"{option_type[0]}{index}"
            quote_result.result_rows.append((code, 5, 5, 83000, 120000))
            instruments.append(SimpleNamespace(
                instrument_code=code, underlying_instrument_code="U", strike_price=100 + index,
                expiry_date=date(2026, 12, 1), listing_date=None,
                option_type=option_type, status="inactive",
            ))
    async_client = SimpleNamespace(query=AsyncMock(return_value=quote_result))
    monkeypatch.setattr("src.analytics.mispricing_universe.get_async_client", AsyncMock(return_value=async_client))

    class Scalars:
        def all(self): return instruments
    class Session:
        def __enter__(self): return self
        def __exit__(self, *args): return None
        def execute(self, statement): return SimpleNamespace(scalars=lambda: Scalars())
    monkeypatch.setattr("src.analytics.mispricing_universe.SessionLocal", Session)

    preview = await discover_option_universe(date(2026, 7, 8))

    assert preview["contract_count"] == 14
    assert preview["groups"][0]["eligible"] is True
    assert preview["groups"][0]["strike_count"] == 7
    assert "missing_listing_date" in preview["groups"][0]["warnings"]
    assert "status" not in async_client.query.await_args.args[0].lower()


async def test_observation_query_supports_all_detail_filters_and_pagination(mock_async_client):
    mock_async_client.query.return_value = SimpleNamespace(column_names=["instrument_code"], result_rows=[("C1",)])
    rows = await get_observations(
        run_id=CONVENTION, underlying_instrument_code="U", expiry_date=date(2026, 12, 1),
        option_type="call", snapshot_time=datetime(2026, 7, 8, 9, 0, tzinfo=TEHRAN),
        quality_status="warning", minimum_absolute_distance_bps=50, offset=25, limit=25,
    )
    assert rows == [{"instrument_code": "C1"}]
    query = mock_async_client.query.await_args.args[0]
    params = mock_async_client.query.await_args.kwargs["parameters"]
    for fragment in ("underlying_instrument_code", "expiry_date", "option_type", "snapshot_time", "quality_status", "abs(midpoint_distance_bps)"):
        assert fragment in query
    assert params["off"] == 25 and params["lim"] == 25 and params["min_distance"] == 50


def test_mispricing_admin_template_and_manual_render_pattern():
    _TEMPLATE_ENV.get_template("option/mispricing.html")
    source = Path("src/admin/option/mispricing_views.py").read_text()
    assert "self._admin_ref" in source
    assert "_render(\"option/mispricing.html\"" in source


def test_mispricing_migration_has_four_dedicated_tables():
    source = Path("src/db/clickhouse/migrations/versions/016_option_mispricing.py").read_text()
    for table in (
        "option_mispricing_universe", "option_mispricing_fits",
        "option_mispricing_observations", "option_mispricing_rankings",
    ):
        assert f"CREATE TABLE IF NOT EXISTS {table}" in source
