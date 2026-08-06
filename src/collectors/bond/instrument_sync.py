from typing import Any

from sqlalchemy.orm import Session

from src.collectors.bond.tsetmc_client import TsetmcClient
from src.collectors.bond.transformer import instrument_info_to_pg_attrs, search_item_to_pg_attrs
from src.db.models.bond import BondInstrument
from src.db.session import SessionLocal
from src.services.operation_runs import RunProgressReporter


async def sync_instruments_to_pg(
    client: TsetmcClient | None = None,
    progress: RunProgressReporter | None = None,
) -> dict[str, Any]:
    errors: list[str] = []
    synced = 0

    own_client = client is None
    if own_client:
        client = TsetmcClient()
        await client.__aenter__()

    try:
        assert client is not None
        search_results = await client.search_instruments("اخزا")
        if progress:
            progress.set_total(len(search_results))

        for item in search_results:
            warning_count = 0
            try:
                code = item.ins_code
                partial_attrs = search_item_to_pg_attrs(
                    ins_code=code,
                    name_fa=item.name_fa,
                    symbol=item.symbol,
                    flow=item.flow,
                    flow_title=item.flow_title,
                    cgr_val_cot=item.cgr_val_cot,
                    cgr_val_cot_title=item.cgr_val_cot_title,
                    last_date=item.last_date,
                )

                info = await client.get_instrument_info(code)
                if info is not None:
                    full_attrs = instrument_info_to_pg_attrs(info, status=partial_attrs["status"])
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
    finally:
        if own_client:
            await client.__aexit__(None, None, None)


def _upsert_instrument(attrs: dict[str, Any]) -> None:
    session: Session
    with SessionLocal() as session:
        session.merge(BondInstrument(**attrs))
        session.commit()
