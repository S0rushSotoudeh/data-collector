from sqladmin import ModelView

from src.db.models.gold import GoldInstrument


class GoldInstrumentAdmin(ModelView, model=GoldInstrument):
    name = "Gold Instrument"
    name_plural = "Gold Instruments"
    icon = "fa-solid fa-coins"
    category = "Gold Market"
    category_icon = "fa-solid fa-coins"
    column_list = [
        GoldInstrument.instrument_code,
        GoldInstrument.symbol,
        GoldInstrument.name_fa,
        GoldInstrument.status,
        GoldInstrument.last_trade_date,
        GoldInstrument.created_at,
    ]
    column_searchable_list = [
        GoldInstrument.instrument_code,
        GoldInstrument.symbol,
        GoldInstrument.name_fa,
        GoldInstrument.name_en,
        GoldInstrument.isin,
    ]
    column_sortable_list = [
        GoldInstrument.instrument_code,
        GoldInstrument.symbol,
        GoldInstrument.status,
        GoldInstrument.last_trade_date,
        GoldInstrument.security_type_code,
        GoldInstrument.created_at,
    ]
    column_default_sort = [(GoldInstrument.symbol, False)]
    can_create = True
    can_edit = True
    can_delete = False
    can_export = True
    page_size = 50
