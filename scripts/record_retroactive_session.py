"""
Registro retroativo da primeira sessao (A/B/C na py_debug_001), rodada
antes do recorder existir. Dados agregados vieram da saida impressa no
terminal e do run_c.log; nao ha objetos Generation brutos por chamada
para no_think/think porque o processo daquela sessao ja tinha
terminado quando o recorder foi criado.

Depois desta sessao, record_episode() ja roda embutido no
run_strategies_py_debug_001.py -- este script e so para nao perder os
3 primeiros pontos de dado.
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, "C:/Users/panta/pandaforge/src")
from pandaforge.metrics.env import capture_environment  # noqa: E402

RESULTS_DIR = Path("C:/Users/panta/pandaforge/results")
RESULTS_DIR.mkdir(parents=True, exist_ok=True)
PATH = RESULTS_DIR / "py_debug_001.jsonl"

HYPOTHESIS = (
    "Um modelo pequeno com reasoning limitado, estado externo e ciclos "
    "iterativos pode resolver tarefas que o mesmo modelo, usando /no_think "
    "ou uma unica janela de reasoning, nao consegue -- dentro dos mesmos "
    "recursos computacionais."
)

env = capture_environment().as_dict()
now = datetime.now(timezone.utc).isoformat()

records = [
    {
        "timestamp": now,
        "task": "py_debug_001",
        "strategy": "no_think",
        "model": "qwen3:4b",
        "hypothesis": HYPOTHESIS,
        "config": {},
        "environment": env,
        "result": {"passed": False, "returncode": 1, "n_passed": None, "n_failed": None},
        "total_tokens_predicted": 347,
        "total_wall_s": 193.6,
        "n_calls": 1,
        "parse_ok": True,
        "generations": None,
        "notes": "Registro retroativo (agregados do terminal; sem objetos Generation "
                 "brutos -- o processo ja tinha terminado quando o recorder foi criado). "
                 "Bug real (apply_discount) NAO foi corrigido.",
        "recorded_retroactively": True,
    },
    {
        "timestamp": now,
        "task": "py_debug_001",
        "strategy": "think",
        "model": "qwen3:4b",
        "hypothesis": HYPOTHESIS,
        "config": {"think_budget": 800},
        "environment": env,
        "result": {"passed": True, "returncode": 0, "n_passed": 3, "n_failed": 0},
        "total_tokens_predicted": 758,
        "total_wall_s": 452.48,
        "n_calls": 1,
        "parse_ok": True,
        "generations": None,
        "notes": "Registro retroativo. Unica estrategia que corrigiu o bug real "
                 "sem introduzir regressao, nesta tarefa.",
        "recorded_retroactively": True,
    },
    {
        "timestamp": now,
        "task": "py_debug_001",
        "strategy": "iterative",
        "model": "qwen3:4b",
        "hypothesis": HYPOTHESIS,
        "config": {"think_budget": 400, "continue_budget": 150, "max_cycles": 5},
        "environment": env,
        "result": {"passed": False, "returncode": 1, "n_passed": 1, "n_failed": 2},
        "total_tokens_predicted": 2025,
        "total_wall_s": 547.26,
        "n_calls": 9,
        "parse_ok": True,
        "generations": None,
        "notes": (
            "Registro retroativo, reconstruido do log por ciclo (run_c.log):\n"
            "ciclo 1: run_tests (247 tok, 59.8s) -- viu a falha original (so apply_discount).\n"
            "ciclo 2: write_file src/orders.py, arquivo INTEIRO (400+68 tok cortado+continuado, 143.0s).\n"
            "ciclo 3: write_file src/orders.py de novo, arquivo INTEIRO (400+68 tok, 120.4s).\n"
            "ciclo 4: read_file src/orders.py (400+29 tok, 109.9s).\n"
            "ciclo 5: run_tests -- 2 falhas (total_price_basic e format_price_basic quebraram; "
            "format_price passou a devolver '19.90' em vez de '$19.90').\n"
            "RESULTADO NEGATIVO: reescrever o arquivo inteiro por ciclo (sem diff/patch parcial) "
            "introduziu regressao em funcoes que ja estavam corretas. Custou 2.7x mais tokens e "
            "20% mais tempo que 'think', e ainda assim saiu pior. Nao suporta a hipotese central "
            "NESTA configuracao -- ver docs/NEGATIVE_RESULTS.md.",
        ),
        "recorded_retroactively": True,
    },
]

with PATH.open("a", encoding="utf-8") as f:
    for r in records:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")

print(f"3 registros retroativos gravados em {PATH}")
