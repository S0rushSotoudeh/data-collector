from src.routes.admin_tasks import router


def test_admin_task_routes_use_explicit_domains() -> None:
    paths = {route.path for route in router.routes}

    assert "/admin/tasks/sync-bond-instruments" in paths
    assert "/admin/tasks/backfill-bond-order-books" in paths
    assert "/admin/tasks/backfill-bond-trades" in paths
    assert "/admin/tasks/sync-option-instruments" in paths
    assert "/admin/tasks/sync-stock-instruments" in paths
    assert "/admin/tasks/compute-yield-curve-snapshot" in paths
    assert "/admin/tasks/backfill-yield-curves" in paths

    assert "/admin/tasks/sync-instruments" not in paths
    assert "/admin/tasks/backfill-order-books" not in paths
    assert "/admin/tasks/backfill-trades" not in paths
