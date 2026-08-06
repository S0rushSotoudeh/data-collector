from datetime import date
from unittest.mock import ANY, AsyncMock, patch

from src.tasks import backfill_stock_order_books_task, backfill_stock_trades_task


def test_backfill_stock_order_books_task_forwards_parsed_dates() -> None:
    expected = {"total_rows": 12, "errors": []}
    collector = AsyncMock(return_value=expected)

    with patch("src.tasks.backfill_stock_order_books", collector):
        result = backfill_stock_order_books_task.run("2025-01-02", "2025-01-04")

    assert result == expected
    collector.assert_awaited_once_with(
        start_date=date(2025, 1, 2),
        end_date=date(2025, 1, 4),
        progress=ANY,
    )


def test_backfill_stock_trades_task_forwards_parsed_dates() -> None:
    expected = {"total_rows": 34, "skipped": 2, "errors": []}
    collector = AsyncMock(return_value=expected)

    with patch("src.tasks.backfill_stock_trades", collector):
        result = backfill_stock_trades_task.run("2025-02-10", "2025-02-11")

    assert result == expected
    collector.assert_awaited_once_with(
        start_date=date(2025, 2, 10),
        end_date=date(2025, 2, 11),
        progress=ANY,
    )
