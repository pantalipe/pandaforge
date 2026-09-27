import sys
sys.path.insert(0, "C:/Users/panta/pandaforge/src")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from pandaforge.tools.protocol import parse_action_simple

samples = [
    "ACAO: read_file src/orders.py",
    "Vou olhar o teste primeiro.\nACAO: run_tests\n",
    "ACAO: done",
    """Vou corrigir o desconto.
ACAO: patch src/orders.py
<<<<<<<
    return round(total - (total * discount_fraction / 100), 2)
=======
    return round(total - (total * discount_fraction), 2)
>>>>>>>
""",
]

for s in samples:
    try:
        a = parse_action_simple(s)
        print(f"OK: tool={a.tool} path={a.path} old={a.old!r} new={a.content!r}")
    except Exception as e:
        print(f"ERRO: {e}")
