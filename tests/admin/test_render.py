from src.admin._render import _TEMPLATE_ENV


def test_sqladmin_original_layout_alias_resolves() -> None:
    template = _TEMPLATE_ENV.get_template("sqladmin_original/layout.html")

    assert template.name == "layout.html"


def test_custom_stock_order_book_template_compiles() -> None:
    template = _TEMPLATE_ENV.get_template("stock_order_book_list.html")

    assert template.name == "stock_order_book_list.html"
