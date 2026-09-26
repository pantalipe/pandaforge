"""Utilidades de calculo de pedidos -- fixture da tarefa py_debug_001.

Um dos bugs aqui e silencioso: nao lanca excecao, so devolve um numero
errado. E deliberado -- o objetivo e forcar quem depura a checar os
VALORES, nao so ler um traceback.
"""


def total_price(orders):
    """Soma (preco * quantidade) de uma lista de pedidos."""
    total = 0
    for order in orders:
        total += order["price"] * order["qty"]
    return round(total, 2)


def apply_discount(total, discount_fraction):
    """
    Aplica um desconto a um total.

    `discount_fraction` e uma fracao de 0.0 a 1.0 (ex.: 0.2 = 20% de
    desconto) -- e assim que os chamadores desta funcao usam.
    """
    # BUG: divide por 100 de novo, como se discount_fraction ainda
    # estivesse numa escala de 0-100. Para discount_fraction=0.2, isso
    # aplica um desconto de 0.2% em vez de 20% -- resultado numerico
    # errado, sem excecao nenhuma.
    return round(total - (total * discount_fraction / 100), 2)


def format_price(value):
    """Formata um valor numerico como string de preco (ex.: '$19.90')."""
    return f"${value:.2f}"
