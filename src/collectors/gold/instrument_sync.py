import logging
from typing import Any

import httpx
from sqlalchemy.orm import Session

from src.collectors.stock.market_watch_client import StockTsetmcClient
from src.collectors.gold.transformer import (
    instrument_info_to_pg_attrs,
    is_gold,
    market_watch_to_pg_attrs,
    parse_ime_funds_html,
)
from src.db.models.gold import GoldInstrument
from src.db.session import SessionLocal
from src.services.operation_runs import RunProgressReporter

logger = logging.getLogger(__name__)

IME_ETF_URL = "https://www.ime.co.ir/ExchangeTradedFunds.html"
IME_HEADERS = {"User-Agent": "Mozilla/5.0 (official-gold-instrument-export)"}


async def sync_gold_instruments_to_pg(
    client: StockTsetmcClient | None = None,
    progress: RunProgressReporter | None = None,
) -> dict[str, Any]:
    errors: list[str] = []
    synced = 0

    own_client = client is None
    if own_client:
        client = StockTsetmcClient()
        await client.__aenter__()

    try:
        assert client is not None
        funds_by_code: dict[str, dict[str, Any]] = {}

        # 1. Fetch official 35 gold funds from IME universe
        try:
            async with httpx.AsyncClient(headers=IME_HEADERS, verify=False, timeout=30.0) as http_client:
                resp = await http_client.get(IME_ETF_URL)
                if resp.status_code == 200:
                    ime_funds = parse_ime_funds_html(resp.text)
                    for fund in ime_funds:
                        funds_by_code[fund["ins_code"]] = {
                            "instrument_code": fund["ins_code"],
                            "name_fa": fund["symbol"],
                            "symbol": fund["symbol"],
                            "status": "active",
                        }
        except Exception as e:
            logger.warning("Could not fetch IME official fund universe: %s", e)

        # 2. Also check TSETMC MarketWatch for any additional items
        try:
            market_watch = await client.get_market_watch()
            for item in market_watch:
                if is_gold(item) and item.ins_code not in funds_by_code:
                    funds_by_code[item.ins_code] = market_watch_to_pg_attrs(item)
        except Exception as e:
            logger.warning("Could not fetch TSETMC market watch: %s", e)

        total_items = list(funds_by_code.values())
        if progress:
            progress.set_total(len(total_items))

        for partial_attrs in total_items:
            warning_count = 0
            code = partial_attrs["instrument_code"]
            try:
                info = await client.get_instrument_info(code)
                if info is not None:
                    full_attrs = instrument_info_to_pg_attrs(info, status=partial_attrs.get("status", "active"))
                else:
                    full_attrs = partial_attrs

                _upsert_instrument(full_attrs)
                synced += 1
            except Exception as e:
                errors.append(f"{code}: {e}")
                warning_count = 1
            finally:
                if progress:
                    progress.advance(output_count=1 if warning_count == 0 else 0, warning_count=warning_count)

        return {"synced": synced, "errors": errors}
    finally:
        if own_client:
            await client.__aexit__(None, None, None)


def _upsert_instrument(attrs: dict[str, Any]) -> None:
    session: Session
    with SessionLocal() as session:
        existing = session.get(GoldInstrument, attrs["instrument_code"])
        if existing is None:
            session.add(GoldInstrument(**attrs))
        else:
            for k, v in attrs.items():
                if k not in ("created_at", "instrument_code"):
                    setattr(existing, k, v)
        session.commit()
