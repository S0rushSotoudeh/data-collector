from datetime import date
from unittest.mock import ANY, AsyncMock, patch

from src.tasks import (
    backfill_gold_order_books_task,
    backfill_gold_trades_task,
    sync_gold_instruments,
)


def test_sync_gold_instruments_task() -> None:
    expected = {"synced": 10, "errors": []}
    collector = AsyncMock(return_value=expected)

    with patch("src.tasks.sync_gold_instruments_to_pg", collector):
        result = sync_gold_instruments.run()

    assert result == expected
    collector.assert_awaited_once_with(progress=ANY)


def test_backfill_gold_order_books_task() -> None:
    expected = {"total_rows": 20, "errors": []}
    collector = AsyncMock(return_value=expected)

    with patch("src.tasks.get_gold_codes_active_in_range", AsyncMock(return_value=["GLD1", "GLD2"])), \
         patch("src.tasks.backfill_gold_order_books", collector):
        result = backfill_gold_order_books_task.run("2026-08-01", "2026-08-05")

    assert result["total_rows"] == 20
    assert result["instrument_count"] == 2
    collector.assert_awaited_once_with(
        start_date=date(2026, 8, 1),
        end_date=date(2026, 8, 5),
        instrument_codes=["GLD1", "GLD2"],
        progress=ANY,
    )


def test_backfill_gold_trades_task() -> None:
    expected = {"total_rows": 50, "skipped": 1, "errors": []}
    collector = AsyncMock(return_value=expected)

    with patch("src.tasks.get_gold_codes_active_in_range", AsyncMock(return_value=["GLD1"])), \
         patch("src.tasks.backfill_gold_trades", collector):
        result = backfill_gold_trades_task.run("2026-08-01", "2026-08-05")

    assert result["total_rows"] == 50
    assert result["instrument_count"] == 1
    collector.assert_awaited_once_with(
        start_date=date(2026, 8, 1),
        end_date=date(2026, 8, 5),
        instrument_codes=["GLD1"],
        progress=ANY,
    )
