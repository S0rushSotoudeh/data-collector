import math
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.analytics.engine import compute_curve_for_date

FACE = 1_000_000
TRADE_DATE = date(2024, 1, 1)


def _bond(code, symbol, maturity_year):
    return SimpleNamespace(
        instrument_code=code,
        symbol=symbol,
        maturity_date=date(maturity_year, 1, 1),
    )


def _bonds():
    return [
        _bond("B1", "SYMB1", 2025),
        _bond("B2", "SYMB2", 2026),
        _bond("B3", "SYMB3", 2028),
        _bond("B4", "SYMB4", 2032),
        _bond("B5", "SYMB5", 2040),
    ]


def _prices():
    return {
        "B1": 950000,
        "B2": 900000,
        "B3": 870000,
        "B4": 840000,
        "B5": 800000,
    }


def _build_ch_mock():
    ch = AsyncMock()
    prices = _prices()
    order_book_rows = []
    for code in prices:
        order_book_rows.append(
            (code, 90000, prices[code], 100, prices[code], 100)
        )

    def _query(sql, parameters=None, **kwargs):
        result = MagicMock()
        if "DISTINCT instrument_code" in sql:
            result.result_rows = [(c,) for c in prices]
        else:
            result.result_rows = order_book_rows
        return result

    ch.query = AsyncMock(side_effect=_query)
    return ch


def _build_session_mock(bonds):
    session = MagicMock()
    execute_result = MagicMock()
    scalars_result = MagicMock()
    scalars_result.all.return_value = bonds
    execute_result.scalars.return_value = scalars_result
    session.execute.return_value = execute_result
    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=session)
    ctx.__exit__ = MagicMock(return_value=False)
    factory = MagicMock(return_value=ctx)
    return factory


@pytest.mark.asyncio
async def test_compute_curve_success_path():
    ch = _build_ch_mock()
    session_factory = _build_session_mock(_bonds())
    insert_fits = MagicMock()
    insert_bonds = MagicMock()

    with (
        patch("src.analytics.engine.get_async_client", AsyncMock(return_value=ch)),
        patch("src.analytics.engine.SessionLocal", session_factory),
        patch("src.analytics.engine.insert_yield_curve_fits", insert_fits),
        patch("src.analytics.engine.insert_yield_curve_bonds", insert_bonds),
    ):
        result = await compute_curve_for_date(TRADE_DATE.isoformat())

    assert result["fits"] == 2
    assert result["bonds"] == 10
    assert "error" not in result

    insert_fits.assert_called_once()
    fit_rows = insert_fits.call_args.args[0]
    assert len(fit_rows) == 2
    sides = {r["curve_side"] for r in fit_rows}
    assert sides == {"bid", "ask"}
    for r in fit_rows:
        assert r["converged"] == 1
        assert r["n_bonds"] == 5
        assert r["n_bonds_total"] == 5
        assert r["error_message"] == ""
        assert r["trade_time"] == 90000

    insert_bonds.assert_called_once()
    bond_rows = insert_bonds.call_args.args[0]
    assert len(bond_rows) == 10
    for r in bond_rows:
        assert "signal" not in r
        assert r["spread_bps"] is not None
        assert r["fitted_yield"] is not None


@pytest.mark.asyncio
async def test_compute_curve_empty_universe():
    ch = AsyncMock()
    empty = MagicMock()
    empty.result_rows = []
    ch.query = AsyncMock(return_value=empty)
    insert_fits = MagicMock()
    insert_bonds = MagicMock()

    with (
        patch("src.analytics.engine.get_async_client", AsyncMock(return_value=ch)),
        patch("src.analytics.engine.SessionLocal", _build_session_mock([])),
        patch("src.analytics.engine.insert_yield_curve_fits", insert_fits),
        patch("src.analytics.engine.insert_yield_curve_bonds", insert_bonds),
    ):
        result = await compute_curve_for_date(TRADE_DATE.isoformat())

    assert result["fits"] == 0
    assert result["error"] == "No instruments found"
    insert_fits.assert_not_called()
    insert_bonds.assert_not_called()


@pytest.mark.asyncio
async def test_compute_curve_too_few_bonds():
    ch = _build_ch_mock()
    insert_fits = MagicMock()
    insert_bonds = MagicMock()

    with (
        patch("src.analytics.engine.get_async_client", AsyncMock(return_value=ch)),
        patch("src.analytics.engine.SessionLocal", _build_session_mock(_bonds()[:3])),
        patch("src.analytics.engine.insert_yield_curve_fits", insert_fits),
        patch("src.analytics.engine.insert_yield_curve_bonds", insert_bonds),
    ):
        result = await compute_curve_for_date(TRADE_DATE.isoformat())

    assert result["fits"] == 0
    assert "need >=4" in result["error"]
    insert_fits.assert_not_called()
    insert_bonds.assert_not_called()
