from pathlib import Path

import pytest

from src.admin._render import _TEMPLATE_ENV


CHART_TEMPLATES = [
    "shared/echarts_support.html",
    "option/parity_analysis.html",
    "option/iv_surface.html",
    "option/box_spread.html",
    "bonds/yield_curve_chart.html",
    "bonds/yield_spread_chart.html",
    "bonds/bond_trades_values.html",
    "bonds/bond_trades_ranking.html",
    "ime/price_volume.html",
]


@pytest.mark.parametrize("template_name", CHART_TEMPLATES)
def test_admin_chart_templates_compile(template_name):
    _TEMPLATE_ENV.get_template(template_name)


def test_shared_chart_utility_exposes_dual_axis_zoom():
    source = Path("src/admin/templates/shared/echarts_support.html").read_text()

    for method in ("init", "showEmpty", "grid", "dualAxisZoom"):
        assert method + ":" in source
    assert 'zoomOnMouseWheel: "shift"' in source
    assert 'orient: "vertical"' in source
    assert source.count('filterMode: "none"') == 4


def test_parity_charts_are_full_width_and_use_shared_support():
    source = Path("src/admin/templates/option/parity_analysis.html").read_text()
    chart_ids = [
        "call-price-chart",
        "put-price-chart",
        "underlying-price-chart",
        "ytm-chart",
        "ytm-spread-chart",
        "capacity-chart",
    ]

    assert "col-lg-" not in source
    assert "small-chart" not in source
    assert 'class="parity-chart"' in source
    assert "AdminCharts.dualAxisZoom(" in source
    for chart_id in chart_ids:
        assert chart_id in source
    assert "capital-profit-chart" not in source
    assert '<details class="mb-3"><summary class="btn btn-outline-secondary mb-2">Snapshot diagnostics</summary>' in source
    for text in ("Minimum YTM spread", "Investment / contract", "Profit at expiry / contract", "Legacy edge logic"):
        assert text in source


def test_iv_page_uses_snapshot_and_history_data_instead_of_bulk_run_data() -> None:
    source = Path("src/admin/templates/option/iv_surface.html").read_text()

    assert "/timeline" in source
    assert "/snapshot?snapshot_time=" in source
    assert "/history?expiry_date=" in source
    assert "/points" not in source
    assert "/fits" not in source
    assert "/grid" not in source
    assert "AbortController" in source
    assert "prefetchAround" in source
    assert 'id="expiry"' in source


def test_iv_forward_chart_separates_price_and_percentage_axes() -> None:
    source = Path("src/admin/templates/option/iv_surface.html").read_text()

    assert "name:'Forward price'" in source
    assert "name:'Funding rate',position:'right'" in source
    assert "rateValue=value=>`${(Number(value)*100).toFixed(2)}%`" in source
    assert "name:'Funding rate',type:'line',yAxisIndex:1" in source


def test_iv_raw_point_tooltip_keeps_only_compact_hover_data() -> None:
    source = Path("src/admin/templates/option/iv_surface.html").read_text()

    assert "tooltip:{trigger:'item',formatter:smileTooltip}" in source
    assert "x.iv,x.option_type,x.strike" in source
    for label in ("Type:", "Strike:", "IV:", "log(K/F):"):
        assert label in source


def test_ime_chart_preserves_contract_rows_and_uses_shared_support() -> None:
    source = Path("src/admin/templates/ime/price_volume.html").read_text()

    assert '{% include "shared/echarts_support.html" %}' in source
    assert "AdminCharts.init" in source
    assert "AdminCharts.dualAxisZoom(" in source
    assert "p.jalali_date+'|'+p.offer_id+'|'+p.source_trade_pk" in source
    assert "p.contract_type===contract" in source
    assert "m.contract_type" in source
    assert "m.offer_id" in source
    assert "m.price_toman" in source
    assert "m.quantity" in source


def test_ime_chart_uses_logarithmic_price_axis() -> None:
    source = Path("src/admin/templates/ime/price_volume.html").read_text()

    assert "type:'log',logBase:10,name:'Price (toman, log)'" in source
    assert "function volumeAxisMax(v){return v.max>0?v.max/.3:1}" in source
    assert "type:'value',name:'Volume',position:'right',max:volumeAxisMax" in source


@pytest.mark.parametrize("template_name", CHART_TEMPLATES[1:])
def test_chart_pages_use_shared_support(template_name):
    source = Path("src/admin/templates", template_name).read_text()

    assert '{% include "shared/echarts_support.html" %}' in source
    assert "AdminCharts.init" in source
    assert "AdminCharts.dualAxisZoom(" in source
    assert "echarts.init" not in source
