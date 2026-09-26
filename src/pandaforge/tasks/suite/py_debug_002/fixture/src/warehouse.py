"""Reconciliacao de estoque de um pequeno armazem -- fixture py_debug_002.

Bug silencioso: NAO lanca excecao, so produz numeros errados -- e so
aparece quando um mesmo SKU recebe mais de uma entrada (IN). Requer
rastrear varias transacoes em sequencia pra perceber, nao da pra ver
olhando so a assinatura ou uma linha isolada.
"""


def parse_transactions(lines):
    """Cada linha e 'KIND SKU QTY', ex.: 'IN WIDGET 10'."""
    transactions = []
    for line in lines:
        kind, sku, qty = line.split()
        transactions.append({"kind": kind, "sku": sku, "qty": int(qty)})
    return transactions


def apply_transactions(transactions):
    """Aplica as transacoes em ordem e devolve o estoque final por SKU."""
    stock = {}
    for t in transactions:
        sku, qty, kind = t["sku"], t["qty"], t["kind"]
        if kind == "IN":
            # BUG: sobrescreve o estoque existente em vez de somar --
            # so aparece quando o mesmo SKU recebe uma segunda entrada.
            stock[sku] = qty
        elif kind == "OUT":
            stock[sku] = stock.get(sku, 0) - qty
    return stock


def lowest_stock_alert(stock, threshold):
    """SKUs com estoque <= threshold, em ordem alfabetica."""
    return sorted(sku for sku, qty in stock.items() if qty <= threshold)


def reconcile(lines, threshold):
    transactions = parse_transactions(lines)
    stock = apply_transactions(transactions)
    return lowest_stock_alert(stock, threshold)
