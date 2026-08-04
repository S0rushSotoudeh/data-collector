from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqladmin import ModelView

from src.db.models.operations import OptionPricingConvention


TEHRAN = ZoneInfo("Asia/Tehran")
TSETMC_PRESET_NOTES = (
    "Standard TSETMC equity-option preset. Review exchange notices for contract-specific "
    "adjustments before approval."
)


class OptionPricingConventionAdmin(ModelView, model=OptionPricingConvention):
    name = "Pricing convention"
    name_plural = "Pricing conventions"
    icon = "fa-solid fa-file-signature"
    category = "Options Analytics"
    can_create = False
    can_delete = False
    column_list = [
        OptionPricingConvention.name, OptionPricingConvention.contract_family,
        OptionPricingConvention.effective_from, OptionPricingConvention.effective_to,
        OptionPricingConvention.exercise_style, OptionPricingConvention.black76_compatible,
        OptionPricingConvention.approved, OptionPricingConvention.approver,
    ]
    form_excluded_columns = [
        OptionPricingConvention.convention_id,
        OptionPricingConvention.approver,
        OptionPricingConvention.approved_at,
        OptionPricingConvention.created_at,
        OptionPricingConvention.updated_at,
    ]
    form_args = {
        "name": {"default": "TSETMC Equity Options — Black-76"},
        "contract_family": {"default": "tsetmc_equity_option"},
        "effective_from": {"default": date(2016, 12, 18)},
        "exercise_style": {"default": "European"},
        "settlement_style": {"default": "cash_and_physical"},
        "multiplier": {"default": 1000},
        "tick_size": {"default": 1.0},
        "price_unit": {"default": "IRR"},
        "black76_compatible": {"default": True},
        "reference_source": {
            "default": "Tehran Stock Exchange option contract notices (https://www.tse.ir/)"
        },
        "notes": {"default": TSETMC_PRESET_NOTES},
    }

    async def on_model_change(self, data, model, is_created, request) -> None:
        """Make approval a single deliberate checkbox in the admin UI."""
        if data.get("approved"):
            if is_created or not getattr(model, "approved_at", None):
                data["approved_at"] = datetime.now(TEHRAN)
            data["approver"] = (
                getattr(model, "approver", None)
                or request.session.get("user")
                or "admin"
            )
        else:
            data["approved_at"] = None
            data["approver"] = None
