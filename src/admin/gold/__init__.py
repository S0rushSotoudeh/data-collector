from src.admin.gold.views import (
    GoldInstrumentAdmin,
    GoldOrderBookView,
    GoldTradesView,
)
from src.admin.gold.analytics_views import (
    GoldBestQuotesChartView,
    GoldNormalizedSpreadChartView,
)

__all__ = [
    "GoldInstrumentAdmin",
    "GoldOrderBookView",
    "GoldTradesView",
    "GoldBestQuotesChartView",
    "GoldNormalizedSpreadChartView",
]
