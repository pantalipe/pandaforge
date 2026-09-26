"""
Versao corrigida de orders.py -- usada SO pelo control-check
(scripts/check_task_py_debug_001.py) para provar que o verificador
realmente detecta o conserto certo. Fica fora de fixture/ de proposito:
setup() so copia fixture/, entao isso nunca vaza para o agente.

Unica mudanca em relacao ao original: remove o `/ 100` espurio em
apply_discount, ja que discount_fraction ja vem em escala 0.0-1.0.
"""

def total_price(orders):
    total = 0
    for order in orders:
        total += order["price"] * order["qty"]
    return round(total, 2)


def apply_discount(total, discount_fraction):
    return round(total - (total * discount_fraction), 2)


def format_price(value):
    return f"${value:.2f}"
