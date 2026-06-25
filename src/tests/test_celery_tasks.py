from src.celery_app import celery


def test_all_tasks_registered() -> None:
    task_names = [
        name for name in celery.tasks.keys() if not name.startswith("celery.")
    ]
    expected = {
        "src.tasks.sync_bond_instruments",
        "src.tasks.fetch_yesterday_orderbook",
        "src.tasks.backfill_order_books_task",
        "src.tasks.fetch_yesterday_trades",
        "src.tasks.backfill_trades_task",
        "src.tasks.compute_yield_curve_snapshot",
        "src.tasks.backfill_yield_curves",
    }
    registered = set(task_names)
    assert registered == expected, (
        f"Missing: {expected - registered}. Extra: {registered - expected}"
    )