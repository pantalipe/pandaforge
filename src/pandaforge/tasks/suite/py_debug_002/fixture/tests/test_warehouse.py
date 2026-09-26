import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from warehouse import (  # noqa: E402
    parse_transactions,
    apply_transactions,
    lowest_stock_alert,
    reconcile,
)


def test_parse_transactions_basic():
    lines = ["IN WIDGET 10", "OUT WIDGET 3"]
    parsed = parse_transactions(lines)
    assert parsed == [
        {"kind": "IN", "sku": "WIDGET", "qty": 10},
        {"kind": "OUT", "sku": "WIDGET", "qty": 3},
    ]


def test_apply_transactions_simple():
    transactions = parse_transactions(["IN WIDGET 10", "OUT WIDGET 3"])
    stock = apply_transactions(transactions)
    assert stock == {"WIDGET": 7}


def test_apply_transactions_repeated_in():
    lines = ["IN WIDGET 10", "OUT WIDGET 3", "IN GADGET 20", "IN WIDGET 5", "OUT GADGET 8"]
    transactions = parse_transactions(lines)
    stock = apply_transactions(transactions)
    assert stock == {"WIDGET": 12, "GADGET": 12}


def test_lowest_stock_alert_basic():
    stock = {"WIDGET": 12, "GADGET": 12, "GIZMO": 2}
    assert lowest_stock_alert(stock, threshold=5) == ["GIZMO"]


def test_reconcile_end_to_end():
    lines = ["IN WIDGET 10", "OUT WIDGET 3", "IN GADGET 20", "IN WIDGET 5", "OUT GADGET 8"]
    assert reconcile(lines, threshold=5) == []
