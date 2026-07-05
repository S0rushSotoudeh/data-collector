from typing import Any

from sqlalchemy.orm import Session

from src.collectors.option.market_watch_client import OptionTsetmcClient
from src.collectors.option.transformer import (
    instrument_info_to_pg_attrs,
    market_watch_to_pg_attrs,
)
from src.db.models.option import OptionInstrument
from src.db.session import SessionLocal


async def sync_option_instruments_to_pg(
    client: OptionTsetmcClient | None = None,
) -> dict[str, Any]:
    errors: list[str] = []
    synced = 0

    own_client = client is None
    if own_client:
        client = OptionTsetmcClient()
        await client.__aenter__()

    try:
        assert client is not None
        from src.collectors.option.transformer import is_option

        market_watch = await client.get_market_watch()
        option_items = [item for item in market_watch if is_option(item)]

        for item in option_items:
            try:
                code = item.ins_code
                partial_attrs = market_watch_to_pg_attrs(item)
                status = partial_attrs.get("status")

                info = await client.get_instrument_info(code)
                if info is not None:
                    full_attrs = instrument_info_to_pg_attrs(info, status=status)
                else:
                    full_attrs = partial_attrs

                _upsert_instrument(full_attrs)
                synced += 1
            except Exception as e:
                errors.append(f"{getattr(item, 'ins_code', '?')}: {e}")

        return {"synced": synced, "errors": errors}
    finally:
        if own_client:
            await client.__aexit__(None, None, None)


def _upsert_instrument(attrs: dict[str, Any]) -> None:
    session: Session
    with SessionLocal() as session:
        session.merge(OptionInstrument(**attrs))
        session.commit()
