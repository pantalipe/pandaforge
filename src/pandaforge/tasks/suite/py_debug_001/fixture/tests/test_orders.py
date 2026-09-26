import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from orders import total_price, apply_discount, format_price  # noqa: E402


def test_total_price_basic():
    orders = [
        {"name": "Widget", "price": 19.99, "qty": 1},
        {"name": "Gadget", "price": 25.50, "qty": 2},
    ]
    assert total_price(orders) == 70.99


def test_apply_discount_basic():
    # 20% de desconto sobre 100.0 deve dar 80.0
    assert apply_discount(100.0, 0.2) == 80.0


def test_format_price_basic():
    assert format_price(19.9) == "$19.90"
