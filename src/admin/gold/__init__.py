from src.admin.gold.views import (
    GoldInstrumentAdmin,
    GoldOrderBookView,
    GoldTradesView,
)
from src.admin.gold.analytics_views import (
    GoldPriceComparisonChartView,
    GoldKalmanArbitrageChartView,
)

__all__ = [
    "GoldInstrumentAdmin",
    "GoldOrderBookView",
    "GoldTradesView",
    "GoldPriceComparisonChartView",
    "GoldKalmanArbitrageChartView",
]
