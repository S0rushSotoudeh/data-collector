from src.celery_app import celery


def test_all_tasks_registered() -> None:
    task_names = [
        name for name in celery.tasks.keys() if not name.startswith("celery.")
    ]
    expected = {
        "src.tasks.run_gold_kalman",
        "src.tasks.sync_bond_instruments",
        "src.tasks.fetch_yesterday_bond_order_book",
        "src.tasks.backfill_bond_order_books_task",
        "src.tasks.fetch_yesterday_bond_trades",
        "src.tasks.backfill_bond_trades_task",
        "src.tasks.compute_yield_curve_snapshot",
        "src.tasks.backfill_yield_curves",
        "src.tasks.sync_option_instruments",
        "src.tasks.sync_stock_instruments",
        "src.tasks.backfill_stock_order_books_task",
        "src.tasks.backfill_stock_trades_task",
        "src.tasks.fetch_yesterday_option_orderbook",
        "src.tasks.backfill_option_order_books_task",
        "src.tasks.fetch_yesterday_option_trades",
        "src.tasks.backfill_option_trades_task",
            "src.tasks.run_parity_analysis",
            "src.tasks.run_box_spread_analysis",
            "src.tasks.run_iv_surface",
            "src.tasks.run_option_mispricing",
        "src.tasks.fetch_yesterday_stock_orderbook",
        "src.tasks.fetch_yesterday_stock_trades",
        "src.tasks.fetch_yesterday_gold_orderbook",
        "src.tasks.fetch_yesterday_gold_trades",
        "src.tasks.backfill_gold_order_books_task",
        "src.tasks.backfill_gold_trades_task",
        "src.tasks.compute_option_market_potential_daily",
        "src.tasks.sync_ime_producers",
        "src.tasks.backfill_ime_physical_trades",
        "src.tasks.fetch_recent_ime_physical_trades",
        }
    registered = set(task_names)
    assert registered == expected, (
        f"Missing: {expected - registered}. Extra: {registered - expected}"
    )
