"""
Versao corrigida de warehouse.py -- so pro control-check. Fica fora de
fixture/, entao nunca vaza pro agente.

Unica mudanca: no branch IN de apply_transactions, soma ao estoque
existente em vez de sobrescrever.
"""

def parse_transactions(lines):
    transactions = []
    for line in lines:
        kind, sku, qty = line.split()
        transactions.append({"kind": kind, "sku": sku, "qty": int(qty)})
    return transactions


def apply_transactions(transactions):
    stock = {}
    for t in transactions:
        sku, qty, kind = t["sku"], t["qty"], t["kind"]
        if kind == "IN":
            stock[sku] = stock.get(sku, 0) + qty
        elif kind == "OUT":
            stock[sku] = stock.get(sku, 0) - qty
    return stock


def lowest_stock_alert(stock, threshold):
    return sorted(sku for sku, qty in stock.items() if qty <= threshold)


def reconcile(lines, threshold):
    transactions = parse_transactions(lines)
    stock = apply_transactions(transactions)
    return lowest_stock_alert(stock, threshold)
