from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.collectors.ime.client import (
    ImeClient,
    ImeError,
    decode_asmx_response,
    parse_gold_etf_ins_codes,
    to_jalali_string,
)
from src.collectors.ime.service import (
    ALL_HISTORY_START,
    _chunks,
    _upsert_products,
    sync_producers,
    transform_trade,
)


def _trade(**overrides):
    row = {
        "ProducerName": "سیمان مازندران",
        "Symbol": "MAS-CPCANG32.5-L50-00",
        "GoodsName": "سیمان تیپ 2",
        "date": "1405/05/27",
        "DeliveryDate": "1405/06/05",
        "arzehPk": 99123,
        "xTalarReportPK": 88123,
        "ContractType": "نقدی",
        "Price": 35740,
        "Quantity": 1050,
        "TotalPrice": 37527000,
        "Unit": "تن",
        "Currency": "هزار ریال",
        "Talar": "تالار سیمان",
    }
    row.update(overrides)
    return row


def test_decode_nested_asmx_json() -> None:
    response = httpx.Response(
        200,
        json={"d": json.dumps(json.dumps([{"code": 5219, "name": "سیمان مازندران"}]))},
        request=httpx.Request("POST", "https://www.ime.co.ir/test"),
    )

    assert decode_asmx_response(response) == [{"code": 5219, "name": "سیمان مازندران"}]


def test_decode_rejects_unexpected_payload() -> None:
    response = httpx.Response(
        200, json={"result": []}, request=httpx.Request("POST", "https://www.ime.co.ir/test")
    )

    with pytest.raises(ImeError, match="expected 'd'"):
        decode_asmx_response(response)


def test_parse_official_gold_etf_ins_codes() -> None:
    page = """
        <table>
          <tr><td>طلا</td><td>نمونه یک</td><td><a href="/instInfo/123">جزئیات</a></td></tr>
          <tr><td>شاخه طلا</td><td>نمونه دو</td><td><a href="/?i=456">جزئیات</a></td></tr>
          <tr><td>اوراق بهادار</td><td>سهام</td><td><a href="/instInfo/789">جزئیات</a></td></tr>
        </table>
    """

    assert parse_gold_etf_ins_codes(page) == {"123", "456"}


def test_official_gold_etf_row_requires_ins_code() -> None:
    with pytest.raises(ImeError, match="no TSETMC InsCode"):
        parse_gold_etf_ins_codes("<tr><td>طلا</td><td>نمونه</td><td>بدون لینک</td></tr>")


def test_gregorian_dates_are_sent_as_jalali() -> None:
    assert ALL_HISTORY_START == date(2001, 3, 21)
    assert to_jalali_string(date(2001, 3, 21)) == "1380/01/01"
    assert to_jalali_string(date(2026, 8, 18)) == "1405/05/27"


@pytest.mark.asyncio
async def test_client_retries_timeouts_and_preserves_request_dates() -> None:
    http = AsyncMock()
    ok = httpx.Response(
        200,
        json={"d": json.dumps([_trade()])},
        request=httpx.Request("POST", "https://www.ime.co.ir/test"),
    )
    http.post.side_effect = [httpx.ReadTimeout("slow"), ok]
    client = ImeClient(client=http, retries=2, request_delay=0)

    rows = await client.get_physical_trades(5219, date(2026, 8, 18), date(2026, 8, 18))

    assert len(rows) == 1
    assert http.post.call_count == 2
    payload = http.post.call_args.kwargs["json"]
    assert payload["Producer"] == 5219
    assert payload["GregorianFromDate"] == "1405/05/27"
    assert payload["GregorianToDate"] == "1405/05/27"


def test_transform_stores_site_price_without_recalculation() -> None:
    row = transform_trade(_trade(), 5219)

    assert row is not None
    assert row["price_thousand_rial"] == Decimal("35740")
    assert row["quantity"] == Decimal("1050")
    assert row["trade_date"] == date(2026, 8, 18)
    assert json.loads(row["raw_json"])["Price"] == 35740


def test_cash_and_matching_remain_distinct_logical_rows() -> None:
    cash = transform_trade(_trade(), 5219)
    matching = transform_trade(
        _trade(ContractType="نقدی (مچینگ)", Quantity=150, xTalarReportPK=88124), 5219
    )

    assert cash is not None and matching is not None
    cash_key = tuple(cash[field] for field in ("producer_code", "trade_date", "product_symbol", "offer_id", "contract_type"))
    matching_key = tuple(matching[field] for field in ("producer_code", "trade_date", "product_symbol", "offer_id", "contract_type"))
    assert cash_key != matching_key
    assert cash["price_thousand_rial"] == matching["price_thousand_rial"] == Decimal("35740")
    assert cash["quantity"] == Decimal("1050")
    assert matching["quantity"] == Decimal("150")


@pytest.mark.parametrize(
    "raw",
    [_trade(Price=None), _trade(Quantity=0), _trade(date=None)],
)
def test_invalid_price_volume_or_date_is_skipped(raw) -> None:
    assert transform_trade(raw, 5219) is None


def test_backfill_chunks_are_bounded_and_non_overlapping(monkeypatch) -> None:
    monkeypatch.setenv("IME_BACKFILL_CHUNK_DAYS", "365")
    parts = _chunks(date(2020, 1, 1), date(2022, 1, 1))

    assert parts[0] == (date(2020, 1, 1), date(2020, 12, 30))
    assert parts[-1][1] == date(2022, 1, 1)
    assert all((end - start).days < 365 for start, end in parts)
    assert all(parts[index][1].toordinal() + 1 == parts[index + 1][0].toordinal() for index in range(len(parts) - 1))


@pytest.mark.asyncio
async def test_producer_sync_preserves_existing_enabled_selection() -> None:
    existing = type("Producer", (), {"enabled": False, "name": "old", "synced_at": None})()
    stored = {5219: existing}
    session = MagicMock()
    session.get.side_effect = lambda _model, code: stored.get(code)
    session_context = MagicMock()
    session_context.__enter__.return_value = session

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get_producers(self):
            return [{"code": 5219, "name": "سیمان مازندران"}]

    with (
        patch("src.collectors.ime.service.ImeClient", return_value=FakeClient()),
        patch("src.collectors.ime.service.SessionLocal", return_value=session_context),
    ):
        result = await sync_producers()

    assert result["synced"] == 1
    assert existing.enabled is False
    assert existing.name == "سیمان مازندران"
    session.commit.assert_called_once()


def test_older_backfill_does_not_regress_product_metadata() -> None:
    existing = type(
        "Product",
        (),
        {
            "goods_name": "new name",
            "unit": "new unit",
            "currency": "new currency",
            "category": "new category",
            "last_trade_date": date(2026, 8, 18),
        },
    )()
    session = MagicMock()
    session.get.return_value = existing
    session_context = MagicMock()
    session_context.__enter__.return_value = session
    older = transform_trade(_trade(date="1405/05/26"), 5219)
    assert older is not None

    with patch("src.collectors.ime.service.SessionLocal", return_value=session_context):
        _upsert_products(5219, [older])

    assert existing.goods_name == "new name"
    assert existing.last_trade_date == date(2026, 8, 18)
    session.add.assert_not_called()
    session.commit.assert_called_once()
