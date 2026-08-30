import logging
from contextlib import AsyncExitStack
from typing import Any

from sqlalchemy.orm import Session

from src.collectors.ime.client import ImeClient
from src.collectors.stock.market_watch_client import StockTsetmcClient
from src.collectors.stock.transformer import (
    instrument_info_to_pg_attrs,
    is_stock,
    market_watch_to_pg_attrs,
)
from src.db.models.stock import StockInstrument
from src.db.session import SessionLocal
from src.services.operation_runs import RunProgressReporter

logger = logging.getLogger(__name__)


async def sync_stock_instruments_to_pg(
    client: StockTsetmcClient | None = None,
    progress: RunProgressReporter | None = None,
    ime_client: ImeClient | None = None,
) -> dict[str, Any]:
    errors: list[str] = []
    synced = 0

    async with AsyncExitStack() as stack:
        if client is None:
            client = await stack.enter_async_context(StockTsetmcClient())
        if ime_client is None:
            ime_client = await stack.enter_async_context(ImeClient())

        assert client is not None
        gold_etf_codes = await ime_client.get_gold_etf_ins_codes()
        market_watch = await client.get_market_watch()
        stock_items = [item for item in market_watch if is_stock(item)]
        if progress:
            progress.set_total(len(stock_items))

        for item in stock_items:
            warning_count = 0
            try:
                code = item.ins_code
                is_gold_etf = code in gold_etf_codes
                partial_attrs = market_watch_to_pg_attrs(item, is_gold_etf=is_gold_etf)
                status = partial_attrs.get("status")

                info = await client.get_instrument_info(code)
                if info is not None:
                    full_attrs = instrument_info_to_pg_attrs(
                        info, status=status, is_gold_etf=is_gold_etf
                    )
                else:
                    full_attrs = partial_attrs

                _upsert_instrument(full_attrs)
                synced += 1
            except Exception as e:
                errors.append(f"{getattr(item, 'ins_code', '?')}: {e}")
                warning_count = 1
            finally:
                if progress:
                    progress.advance(output_count=1 if warning_count == 0 else 0, warning_count=warning_count)

        return {"synced": synced, "errors": errors}


def _upsert_instrument(attrs: dict[str, Any]) -> None:
    session: Session
    with SessionLocal() as session:
        session.merge(StockInstrument(**attrs))
        session.commit()
