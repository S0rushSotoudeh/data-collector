from __future__ import annotations

import math
from collections import defaultdict
from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select

from src.db.clickhouse import get_client
from src.db.clickhouse.iv_surface import CONTRACT_DAILY_TABLE, PAIR_DAILY_TABLE
from src.db.models.option import OptionInstrument
from src.db.session import SessionLocal

TEHRAN = ZoneInfo("Asia/Tehran")


def compute_daily(day: date) -> dict[str, int]:
    client = get_client()
    with SessionLocal() as session:
        instruments = session.execute(select(OptionInstrument)).scalars().all()
    meta = {item.instrument_code: item for item in instruments if item.expiry_date and item.strike_price}
    codes = list(meta)
    if not codes:
        return {"contracts": 0, "pairs": 0}
    trades = client.query(
        "SELECT instrument_code, count(), sum(volume), sum(value), "
        "if(sum(volume)>0, sum(price*volume)/sum(volume), NULL) FROM option_trades FINAL "
        "WHERE trade_date={day:Date} AND is_canceled=0 AND instrument_code IN {codes:Array(String)} GROUP BY instrument_code",
        parameters={"day": day, "codes": codes},
    ).result_rows
    books = client.query(
        "SELECT instrument_code, quantile(.25)(spread), quantile(.5)(spread), quantile(.75)(spread), "
        "avg(bid_depth), avg(ask_depth), avg(two_sided) FROM ("
        "SELECT instrument_code, trade_time, "
        "if(max(ask_price)>0 AND max(bid_price)>0 AND max(ask_price)>=max(bid_price), "
        "(max(ask_price)-max(bid_price))/greatest((max(ask_price)+max(bid_price))/2,1), NULL) spread, "
        "sum(bid_volume) bid_depth, sum(ask_volume) ask_depth, "
        "toUInt8(max(bid_price)>0 AND max(ask_price)>0 AND max(ask_price)>=max(bid_price)) two_sided "
        "FROM option_order_book FINAL WHERE trade_date={day:Date} AND instrument_code IN {codes:Array(String)} "
        "GROUP BY instrument_code, trade_time) GROUP BY instrument_code",
        parameters={"day": day, "codes": codes},
    ).result_rows
    trade_map = {row[0]: row[1:] for row in trades}
    book_map = {row[0]: row[1:] for row in books}
    now = datetime.now(TEHRAN)
    contract_rows = []
    metrics = {}
    for code, item in meta.items():
        trade_count, volume, value, vwap = trade_map.get(code, (0, 0, 0, None))
        p25, p50, p75, bid_depth, ask_depth, two_sided = book_map.get(code, (None, None, None, 0, 0, 0))
        flags = []
        if not item.underlying_instrument_code: flags.append("unmapped_underlying")
        if not two_sided: flags.append("no_two_sided_quotes")
        activity = math.log1p(float(value or 0)) + math.log1p(float(trade_count or 0))
        liquidity = float(two_sided or 0) * math.log1p(min(float(bid_depth or 0), float(ask_depth or 0)))
        metrics[code] = (trade_count, value, two_sided, bid_depth, ask_depth, activity)
        contract_rows.append((
            day, code, item.underlying_instrument_code or "", (item.option_type or "").lower(),
            float(item.strike_price), item.expiry_date, int(trade_count or 0), int(volume or 0), float(value or 0),
            float(vwap) if vwap is not None else None, p25, p50, p75, float(bid_depth or 0), float(ask_depth or 0),
            float(two_sided or 0), activity, liquidity, flags, now,
        ))
    client.insert(CONTRACT_DAILY_TABLE, contract_rows, column_names=[
        "trade_date", "instrument_code", "underlying_instrument_code", "option_type", "strike", "expiry_date",
        "trade_count", "traded_volume", "traded_value", "vwap", "spread_p25", "spread_p50", "spread_p75",
        "bid_depth", "ask_depth", "two_sided_ratio", "activity_score", "liquidity_score", "quality_flags", "computed_at",
    ])
    grouped: dict[tuple, dict[str, OptionInstrument]] = defaultdict(dict)
    for item in meta.values():
        side = "call" if (item.option_type or "").lower() in {"call", "c"} else "put"
        grouped[(item.underlying_instrument_code or "", item.expiry_date, float(item.strike_price))][side] = item
    pair_rows = []
    for (underlying, expiry, strike), pair in grouped.items():
        if set(pair) != {"call", "put"}:
            continue
        call, put = pair["call"], pair["put"]
        cm, pm = metrics[call.instrument_code], metrics[put.instrument_code]
        quote_availability = min(float(cm[2] or 0), float(pm[2] or 0))
        bid_depth, ask_depth = min(float(cm[3] or 0), float(pm[3] or 0)), min(float(cm[4] or 0), float(pm[4] or 0))
        trade_count, value, activity = int(cm[0] + pm[0]), float(cm[1] + pm[1]), float(cm[5] + pm[5])
        flags = []
        if not underlying: flags.append("unmapped_underlying")
        if quote_availability < .5: flags.append("sparse_quotes")
        eligible = bool(underlying and quote_availability >= .5 and bid_depth > 0 and ask_depth > 0 and trade_count > 0)
        pair_rows.append((day, underlying, call.instrument_code, put.instrument_code, strike, expiry,
                          "mapped" if underlying else "unmapped", trade_count, value, quote_availability,
                          bid_depth, ask_depth, activity, int(eligible), flags, now))
    if pair_rows:
        client.insert(PAIR_DAILY_TABLE, pair_rows, column_names=[
            "trade_date", "underlying_instrument_code", "call_instrument_code", "put_instrument_code", "strike",
            "expiry_date", "mapping_status", "trade_count", "traded_value", "quote_availability", "bid_depth",
            "ask_depth", "activity_score", "pilot_eligible", "quality_flags", "computed_at",
        ])
    return {"contracts": len(contract_rows), "pairs": len(pair_rows)}
