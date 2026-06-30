import asyncio
import math
from datetime import date, datetime, timezone
from typing import Any

from sqlmodel import select

from src.analytics.yield_curve import (
    FACE_VALUE,
    fit_nelson_siegel,
    ns_yield,
    yield_from_price,
)
from src.db.clickhouse import get_async_client
from src.db.clickhouse.insert import insert_yield_curve_bonds, insert_yield_curve_fits
from src.db.models.bond import BondInstrument
from src.db.session import SessionLocal

_ERROR_MESSAGE_MAX = 200

# Bonds very close to maturity produce distorted yields (price noise is
# amplified by 1/ttm) and corrupt the Nelson-Siegel fit. Exclude them from
# the curve fit. ~30 days.
MIN_TTM_YEARS = 30.0 / 365.25


def _hhmmss_to_seconds(t: int) -> int:
    h = t // 10000
    m = (t % 10000) // 100
    s = t % 100
    return h * 3600 + m * 60 + s


def _seconds_to_hhmmss(s: int) -> int:
    h = s // 3600
    m = (s % 3600) // 60
    s = s % 60
    return h * 10000 + m * 100 + s


def _truncate_error(message: Any) -> str:
    text = str(message)
    if len(text) > _ERROR_MESSAGE_MAX:
        text = text[:_ERROR_MESSAGE_MAX]
    return text


async def _load_universe(trade_date: date, ch: Any) -> dict[str, dict[str, Any]]:
    universe_rows = (
        await ch.query(
            "SELECT DISTINCT instrument_code "
            "FROM bond_order_book FINAL "
            "WHERE trade_date = {d:Date} AND depth_level = 1 "
            "  AND (bid_volume > 0 OR ask_volume > 0)",
            parameters={"d": trade_date},
        )
    ).result_rows
    all_codes = [r[0] for r in universe_rows]

    if not all_codes:
        return {}

    with SessionLocal() as session:
        stmt = select(BondInstrument).where(
            BondInstrument.instrument_code.in_(all_codes)
        )
        bonds = session.execute(stmt).scalars().all()

    bond_map: dict[str, dict[str, Any]] = {}
    for b in bonds:
        if b.maturity_date and b.maturity_date > trade_date:
            ttm = (b.maturity_date - trade_date).days / 365.25
            if ttm >= 1.0 / 365.25:
                bond_map[b.instrument_code] = {
                    "symbol": b.symbol or b.instrument_code,
                    "ttm": ttm,
                }
    return bond_map


async def _load_order_book(
    trade_date: date, bond_map: dict[str, dict[str, Any]], ch: Any
) -> list[dict[str, Any]]:
    raw_rows = (
        await ch.query(
            "SELECT instrument_code, trade_time, bid_price, bid_volume, "
            "       ask_price, ask_volume "
            "FROM bond_order_book FINAL "
            "WHERE trade_date = {d:Date} AND depth_level = 1 "
            "  AND (bid_volume > 0 OR ask_volume > 0) "
            "ORDER BY trade_time ASC, instrument_code ASC",
            parameters={"d": trade_date},
        )
    ).result_rows

    parsed_rows: list[dict[str, Any]] = []
    for r in raw_rows:
        code = r[0]
        if code not in bond_map:
            continue
        parsed_rows.append(
            {
                "code": code,
                "time_sec": _hhmmss_to_seconds(r[1]),
                "time_hhmmss": r[1],
                "bid_price": r[2],
                "bid_volume": r[3],
                "ask_price": r[4],
                "ask_volume": r[5],
            }
        )
    return parsed_rows


def _finite_yield(price: Any, ttm: float) -> float | None:
    """Yield for a (price, ttm) pair, or None if it is not usable."""
    if price is None or price <= 0 or ttm <= 0:
        return None
    ytm = yield_from_price(price, FACE_VALUE, ttm)
    if not math.isfinite(ytm):
        return None
    return ytm


def _bonds_for_bucket(
    bond_map: dict[str, dict[str, Any]],
    state: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Build (bid_bonds, ask_bonds) for a single snapshot.

    A bond is admitted to the curve only when it has a two-sided quote
    (both bid_volume > 0 AND ask_volume > 0). This keeps the bid and ask
    curves on the same liquid universe and prevents orphan points that
    exist on one side only (a bid with no ask volume, or vice versa).

    Each admitted bond then contributes one point to each side, priced off
    its respective side price.
    """
    bid_bonds: list[dict[str, Any]] = []
    ask_bonds: list[dict[str, Any]] = []
    for code, info in bond_map.items():
        snap = state.get(code)
        if not snap:
            continue
        if snap["bid_volume"] <= 0 or snap["ask_volume"] <= 0:
            continue
        ttm = info["ttm"]
        if ttm < MIN_TTM_YEARS:
            continue
        bid_ytm = _finite_yield(snap["bid_price"], ttm)
        ask_ytm = _finite_yield(snap["ask_price"], ttm)
        if bid_ytm is None or ask_ytm is None:
            continue
        symbol = info["symbol"]
        bid_bonds.append(
            {
                "code": code,
                "symbol": symbol,
                "ttm": ttm,
                "price": snap["bid_price"],
                "volume": snap["bid_volume"],
                "yield": bid_ytm,
            }
        )
        ask_bonds.append(
            {
                "code": code,
                "symbol": symbol,
                "ttm": ttm,
                "price": snap["ask_price"],
                "volume": snap["ask_volume"],
                "yield": ask_ytm,
            }
        )
    return bid_bonds, ask_bonds


def _bucket_and_fit(
    parsed_rows: list[dict[str, Any]],
    bond_map: dict[str, dict[str, Any]],
    trade_date: date,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not parsed_rows:
        return [], []

    min_time = min(r["time_sec"] for r in parsed_rows)
    max_time = max(r["time_sec"] for r in parsed_rows)

    start_bucket = (min_time // 30) * 30
    end_bucket = (max_time // 30) * 30
    buckets = list(range(start_bucket, end_bucket + 1, 30))

    state: dict[str, dict[str, Any]] = {}
    processed_idx = 0
    fit_rows: list[dict[str, Any]] = []
    bond_rows: list[dict[str, Any]] = []

    for bucket_seconds in buckets:
        bucket_hhmmss = _seconds_to_hhmmss(bucket_seconds)

        while (
            processed_idx < len(parsed_rows)
            and parsed_rows[processed_idx]["time_sec"] <= bucket_seconds
        ):
            row = parsed_rows[processed_idx]
            code = row["code"]
            state[code] = {
                "bid_price": row["bid_price"],
                "bid_volume": row["bid_volume"],
                "ask_price": row["ask_price"],
                "ask_volume": row["ask_volume"],
            }
            processed_idx += 1

        if not state:
            continue

        bid_bonds, ask_bonds = _bonds_for_bucket(bond_map, state)

        now_ts = datetime.now(timezone.utc)

        for side, bonds_list in (("bid", bid_bonds), ("ask", ask_bonds)):
            fit = _fit_side(bonds_list)

            fit_rows.append(
                {
                    "trade_date": trade_date,
                    "trade_time": bucket_hhmmss,
                    "curve_side": side,
                    "beta0": fit.get("beta0"),
                    "beta1": fit.get("beta1"),
                    "beta2": fit.get("beta2"),
                    "lambda": fit.get("lambda"),
                    "rmse": fit.get("rmse"),
                    "n_bonds": len(bonds_list),
                    "n_bonds_total": len(bond_map),
                    "converged": fit.get("converged", 0),
                    "error_message": fit.get("error_message", ""),
                    "computed_at": now_ts,
                }
            )

            if fit.get("converged") != 1:
                continue

            b0 = fit["beta0"]
            b1 = fit["beta1"]
            b2 = fit["beta2"]
            lam = fit["lambda"]

            for bond in bonds_list:
                fitted_yield = ns_yield(bond["ttm"], b0, b1, b2, lam)
                spread = (bond["yield"] - fitted_yield) * 10000

                bond_rows.append(
                    {
                        "trade_date": trade_date,
                        "trade_time": bucket_hhmmss,
                        "instrument_code": bond["code"],
                        "curve_side": side,
                        "symbol": bond["symbol"],
                        "ttm_years": bond["ttm"],
                        "price": bond["price"],
                        "volume": bond["volume"],
                        "yield": bond["yield"],
                        "fitted_yield": fitted_yield,
                        "spread_bps": spread,
                        "computed_at": now_ts,
                    }
                )

    return fit_rows, bond_rows


def _fit_side(bonds_list: list[dict[str, Any]]) -> dict[str, Any]:
    if len(bonds_list) < 4:
        return {
            "beta0": None,
            "beta1": None,
            "beta2": None,
            "lambda": None,
            "rmse": None,
            "converged": 0,
            "error_message": _truncate_error(
                f"Need at least 4 bonds, got {len(bonds_list)}"
            ),
        }
    try:
        fit = fit_nelson_siegel(
            [b["yield"] for b in bonds_list],
            [b["ttm"] for b in bonds_list],
        )
    except Exception as exc:
        return {
            "beta0": None,
            "beta1": None,
            "beta2": None,
            "lambda": None,
            "rmse": None,
            "converged": 0,
            "error_message": _truncate_error(
                f"{exc.__class__.__name__}: {exc}"
            ),
        }
    if fit.get("error_message"):
        fit["error_message"] = _truncate_error(fit["error_message"])
    return fit


async def _persist(
    fit_rows: list[dict[str, Any]], bond_rows: list[dict[str, Any]]
) -> None:
    if fit_rows:
        await asyncio.to_thread(insert_yield_curve_fits, fit_rows)
    if bond_rows:
        await asyncio.to_thread(insert_yield_curve_bonds, bond_rows)


async def compute_curve_for_date(date_str: str) -> dict:
    trade_date = date.fromisoformat(date_str)
    ch = await get_async_client()

    bond_map = await _load_universe(trade_date, ch)

    if not bond_map:
        return {"date": date_str, "buckets": 0, "fits": 0, "error": "No instruments found"}

    if len(bond_map) < 4:
        return {
            "date": date_str,
            "buckets": 0,
            "fits": 0,
            "error": f"Only {len(bond_map)} bonds with valid maturity (need >=4)",
        }

    parsed_rows = await _load_order_book(trade_date, bond_map, ch)

    if not parsed_rows:
        return {
            "date": date_str,
            "buckets": 0,
            "fits": 0,
            "error": "No raw data after filtering",
        }

    fit_rows, bond_rows = _bucket_and_fit(parsed_rows, bond_map, trade_date)

    await _persist(fit_rows, bond_rows)

    return {
        "date": date_str,
        "buckets": len(fit_rows) // 2 if fit_rows else 0,
        "fits": len(fit_rows),
        "bonds": len(bond_rows),
    }
