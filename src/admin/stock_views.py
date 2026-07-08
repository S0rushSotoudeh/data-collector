from sqladmin import ModelView

from src.db.models.stock import StockInstrument


class StockInstrumentAdmin(ModelView, model=StockInstrument):
    name = "Stock Instrument"
    name_plural = "Stock Instruments"
    icon = "fa-solid fa-chart-simple"
    column_list = [
        StockInstrument.instrument_code,
        StockInstrument.symbol,
        StockInstrument.name_fa,
        StockInstrument.status,
        StockInstrument.security_type_name,
        StockInstrument.last_trade_date,
        StockInstrument.created_at,
    ]
    column_searchable_list = [
        StockInstrument.instrument_code,
        StockInstrument.symbol,
        StockInstrument.name_fa,
        StockInstrument.name_en,
        StockInstrument.isin,
    ]
    column_sortable_list = [
        StockInstrument.instrument_code,
        StockInstrument.symbol,
        StockInstrument.status,
        StockInstrument.last_trade_date,
        StockInstrument.security_type_code,
        StockInstrument.created_at,
    ]
    column_default_sort = [(StockInstrument.symbol, False)]
    can_create = True
    can_edit = True
    can_delete = False
    can_export = True
    page_size = 50
