from sqladmin import Admin

from src.admin.auth import BasicAuthBackend
from src.admin.bond_views import BondInstrumentAdmin
from src.admin.clickhouse_views import BondOrderBookView, BondTradesView
from src.admin.task_views import CeleryTasksView
from src.admin.yield_curve_views import YieldCurveFitsView, YieldCurveBondsView
from src.db.session import engine


def create_admin(
    app: "FastAPI",  # type: ignore[name-defined]
    auth_backend: BasicAuthBackend,
) -> Admin:
    admin = Admin(
        app=app,
        engine=engine,
        authentication_backend=auth_backend,
        title="Data Collector Admin",
    )
    admin.add_view(BondInstrumentAdmin)
    admin.add_view(BondOrderBookView)
    admin.add_view(BondTradesView)
    admin.add_view(YieldCurveFitsView)
    admin.add_view(YieldCurveBondsView)
    admin.add_view(CeleryTasksView)
    return admin
