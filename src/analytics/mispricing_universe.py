from __future__ import annotations

from collections import defaultdict
from datetime import date, time
from typing import Any

from sqlalchemy import select

from src.analytics.parity_engine import hhmmss
from src.db.clickhouse import get_async_client
from src.db.models.option import OptionInstrument
from src.db.session import SessionLocal

_FATAL_METADATA_REASONS = {
    "missing_instrument_metadata", "missing_underlying_mapping", "missing_strike",
    "missing_expiry", "missing_option_type", "listed_after_trade_date", "expired_before_session",
}


async def discover_option_universe(
    trade_date: date,
    start_time: time = time(8, 30),
    end_time: time = time(12, 30),
    expiry_cutoff: time = time(12, 30),
) -> dict[str, Any]:
    """Discover the historical universe from actual level-one rows, never status."""
    client = await get_async_client()
    result = await client.query(
        "SELECT instrument_code, count() quote_count, "
        "countIf(bid_price > 0 AND ask_price > 0 AND bid_price <= ask_price) two_sided_quote_count, "
        "min(trade_time), max(trade_time) FROM option_order_book FINAL "
        "WHERE trade_date = {day:Date} AND depth_level = 1 "
        "AND trade_time >= {start:UInt32} AND trade_time <= {end:UInt32} "
        "GROUP BY instrument_code ORDER BY instrument_code",
        parameters={"day": trade_date, "start": hhmmss(start_time), "end": hhmmss(end_time)},
    )
    quote_rows = {str(row[0]): row for row in result.result_rows}
    codes = list(quote_rows)
    with SessionLocal() as session:
        instruments = session.execute(
            select(OptionInstrument).where(OptionInstrument.instrument_code.in_(codes))
        ).scalars().all() if codes else []
    metadata = {item.instrument_code: item for item in instruments}
    contracts: list[dict[str, Any]] = []
    grouped: dict[tuple[str, date | None], list[dict[str, Any]]] = defaultdict(list)
    for code, quote in quote_rows.items():
        item = metadata.get(code)
        reasons: list[str] = []
        option_type = ""
        underlying = ""
        underlying_symbol = ""
        strike = None
        expiry = None
        listing = None
        if item is None:
            reasons.append("missing_instrument_metadata")
        else:
            underlying = item.underlying_instrument_code or ""
            underlying_symbol = getattr(item, "underlying_symbol", None) or ""
            strike = float(item.strike_price) if item.strike_price is not None else None
            expiry = item.expiry_date
            listing = item.listing_date
            raw_type = (item.option_type or "").lower()
            option_type = "call" if raw_type in {"call", "c"} else "put" if raw_type in {"put", "p"} else ""
            if not underlying:
                reasons.append("missing_underlying_mapping")
            if strike is None or strike <= 0:
                reasons.append("missing_strike")
            if expiry is None:
                reasons.append("missing_expiry")
            if not option_type:
                reasons.append("missing_option_type")
            if listing is None:
                reasons.append("missing_listing_date")
            elif listing > trade_date:
                reasons.append("listed_after_trade_date")
            if expiry is not None and (expiry < trade_date or (expiry == trade_date and expiry_cutoff <= start_time)):
                reasons.append("expired_before_session")
        row = {
            "instrument_code": code,
            "underlying_instrument_code": underlying,
            "underlying_symbol": underlying_symbol,
            "option_type": option_type,
            "strike": strike,
            "expiry_date": expiry,
            "listing_date": listing,
            "quote_count": int(quote[1]),
            "two_sided_quote_count": int(quote[2]),
            "first_quote_time": int(quote[3]),
            "last_quote_time": int(quote[4]),
            "eligible": 0,
            "eligibility_reasons": reasons,
        }
        contracts.append(row)
        grouped[(underlying, expiry)].append(row)

    groups: list[dict[str, Any]] = []
    for (underlying, expiry), rows in sorted(grouped.items(), key=lambda item: (item[0][0], item[0][1] or date.min)):
        # A historical quote is direct evidence the contract was listed that
        # day. Missing listing_date remains visible as a metadata warning, but
        # it must not make an otherwise complete quoted chain unusable.
        complete = [
            row for row in rows
            if not any(reason in _FATAL_METADATA_REASONS for reason in row["eligibility_reasons"])
        ]
        strikes = sorted({row["strike"] for row in complete if row["strike"] is not None})
        calls = [row for row in complete if row["option_type"] == "call"]
        puts = [row for row in complete if row["option_type"] == "put"]
        warnings = sorted({reason for row in rows for reason in row["eligibility_reasons"]})
        reasons: list[str] = []
        if len(strikes) < 7:
            reasons.append("insufficient_strikes")
        if not calls or not puts:
            reasons.append("missing_call_put_coverage")
        reasons = sorted(set(reasons))
        eligible = bool(underlying and expiry and not reasons)
        for row in rows:
            row["group_strike_count"] = len(strikes)
            row["group_call_count"] = len(calls)
            row["group_put_count"] = len(puts)
            row["eligible"] = int(
                eligible and not any(reason in _FATAL_METADATA_REASONS for reason in row["eligibility_reasons"])
            )
            row["eligibility_reasons"] = sorted(set(row["eligibility_reasons"] + ([] if eligible else reasons)))
        groups.append({
            "underlying_instrument_code": underlying,
            "underlying_symbol": next((row["underlying_symbol"] for row in rows if row["underlying_symbol"]), ""),
            "expiry_date": expiry,
            "available_strikes": strikes,
            "strike_count": len(strikes),
            "call_count": len(calls),
            "put_count": len(puts),
            "quote_count": sum(row["quote_count"] for row in rows),
            "two_sided_quote_count": sum(row["two_sided_quote_count"] for row in rows),
            "contract_count": len(rows),
            "eligible": eligible,
            "eligibility_reasons": reasons,
            "warnings": warnings,
        })
    return {
        "trade_date": trade_date,
        "start_time": start_time,
        "end_time": end_time,
        "contract_count": len(contracts),
        "underlying_count": len({row["underlying_instrument_code"] for row in contracts if row["underlying_instrument_code"]}),
        "eligible_group_count": sum(int(group["eligible"]) for group in groups),
        "groups": groups,
        "contracts": contracts,
    }
