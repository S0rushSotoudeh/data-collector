from pathlib import Path

import pytest

from src.admin._render import _TEMPLATE_ENV


CHART_TEMPLATES = [
    "shared/echarts_support.html",
    "option/parity_analysis.html",
    "bonds/yield_curve_chart.html",
    "bonds/yield_spread_chart.html",
    "bonds/bond_trades_values.html",
    "bonds/bond_trades_ranking.html",
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


@pytest.mark.parametrize("template_name", CHART_TEMPLATES[1:])
def test_chart_pages_use_shared_support(template_name):
    source = Path("src/admin/templates", template_name).read_text()

    assert '{% include "shared/echarts_support.html" %}' in source
    assert "AdminCharts.init" in source
    assert "AdminCharts.dualAxisZoom(" in source
    assert "echarts.init" not in source
