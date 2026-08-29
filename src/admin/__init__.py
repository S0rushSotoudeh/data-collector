from sqladmin import Admin
from pathlib import Path

from src.admin.auth import BasicAuthBackend
from src.admin.bonds.bond_views import BondInstrumentAdmin
from src.admin.option.option_views import OptionInstrumentAdmin
from src.admin.stock.stock_views import StockInstrumentAdmin
from src.admin.gold.gold_views import GoldInstrumentAdmin
from src.admin.gold.gold_clickhouse_views import GoldOrderBookView, GoldTradesView
from src.admin.bonds.bond_trades_values_views import BondTradesRankingChartView, BondTradesValuesChartView
from src.admin.bonds.yield_chart_views import YieldCurveChartView, YieldSpreadChartView
from src.admin.bonds.clickhouse_views import BondOrderBookView, BondTradesView
from src.admin.option.option_clickhouse_views import OptionOrderBookView, OptionTradesView
from src.admin.option.parity_views import OptionsAnalyticsView
from src.admin.option.parity_clickhouse_views import ParityAnalysisSnapshotsView
from src.admin.option.iv_views import IVSurfaceView, OptionsMarketPotentialView
from src.admin.option.iv_clickhouse_views import OptionIVPointsView, ORCWingFitsView
from src.admin.option.box_spread_views import BoxCalculatorView, BoxSpreadView
from src.admin.option.mispricing_views import OptionMispricingView
from src.admin.option.box_spread_clickhouse_views import BoxSpreadPricingsView, BoxSpreadSnapshotsView
from src.admin.operations_views import OptionFeeScheduleAdmin, OptionPricingConventionAdmin
from src.admin.run_views import (
    BoxSpreadRunsView, CollectionRunsView, IVORCRunsView, MarketPotentialRunsView, ParityRunsView,
    YieldCurveRunsView, OptionMispricingRunsView,
)
from src.admin.stock.stock_clickhouse_views import StockOrderBookView, StockTradesView
from src.admin.task_views import CeleryTasksView
from src.admin.ime.views import ImeProducerAdmin, ImeProductAdmin, ImeTradesView, ImePriceVolumeView
from src.admin.bonds.yield_curve_views import YieldCurveFitsView, YieldCurveBondsView
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
        templates_dir=str(Path(__file__).parent / "templates"),
    )
    admin.add_view(StockInstrumentAdmin)
    admin.add_view(BondInstrumentAdmin)
    admin.add_view(OptionInstrumentAdmin)
    admin.add_view(BondOrderBookView)
    admin.add_view(BondTradesView)
    admin.add_view(OptionOrderBookView)
    admin.add_view(OptionTradesView)
    admin.add_view(OptionsAnalyticsView)
    admin.add_view(BoxCalculatorView)
    admin.add_view(BoxSpreadView)
    admin.add_view(OptionsMarketPotentialView)
    admin.add_view(IVSurfaceView)
    admin.add_view(OptionMispricingView)
    admin.add_view(OptionIVPointsView)
    admin.add_view(ORCWingFitsView)
    admin.add_view(OptionPricingConventionAdmin)
    admin.add_view(OptionFeeScheduleAdmin)
    admin.add_view(ParityRunsView)
    admin.add_view(ParityAnalysisSnapshotsView)
    admin.add_view(BoxSpreadRunsView)
    admin.add_view(BoxSpreadSnapshotsView)
    admin.add_view(BoxSpreadPricingsView)
    admin.add_view(IVORCRunsView)
    admin.add_view(OptionMispricingRunsView)
    admin.add_view(MarketPotentialRunsView)
    admin.add_view(StockOrderBookView)
    admin.add_view(StockTradesView)
    admin.add_view(GoldInstrumentAdmin)
    admin.add_view(GoldOrderBookView)
    admin.add_view(GoldTradesView)
    admin.add_view(YieldCurveFitsView)
    admin.add_view(YieldCurveBondsView)
    admin.add_view(YieldCurveChartView)
    admin.add_view(YieldSpreadChartView)
    admin.add_view(BondTradesValuesChartView)
    admin.add_view(BondTradesRankingChartView)
    admin.add_view(ImeProducerAdmin)
    admin.add_view(ImeProductAdmin)
    admin.add_view(ImeTradesView)
    admin.add_view(ImePriceVolumeView)
    admin.add_view(CeleryTasksView)
    admin.add_view(CollectionRunsView)
    admin.add_view(YieldCurveRunsView)
    return admin
