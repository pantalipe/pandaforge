"""
Control-check generico da py_debug_002 -- SEM LLM nenhum envolvido.
Mesma logica do check_task_py_debug_001.py, so trocando o alvo.
"""
import sys
sys.path.insert(0, "C:/Users/panta/pandaforge/src")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from pathlib import Path
from pandaforge.tasks import PyDebugTask

TASK_NAME = "py_debug_002"
SOURCE_REL_PATH = "src/warehouse.py"
SOLUTION = Path(f"C:/Users/panta/pandaforge/src/pandaforge/tasks/"
                 f"suite/{TASK_NAME}/solution/warehouse_fixed.py")
EXPECTED_N_FAILED_BROKEN = 2


def main():
    task = PyDebugTask.load(TASK_NAME)
    ok = True

    print("=" * 70)
    print("1) Estado quebrado (fixture original, sem alteracao)")
    print("=" * 70)
    workdir_broken = task.setup()
    result_broken = task.verify(workdir_broken)
    print(result_broken.summary)
    print(result_broken.stdout)
    if result_broken.passed:
        print("*** FALHA DO CONTROL-CHECK: a fixture deveria falhar e passou. ***")
        ok = False
    elif result_broken.n_failed != EXPECTED_N_FAILED_BROKEN:
        print(f"*** AVISO: esperava {EXPECTED_N_FAILED_BROKEN} testes falhando, "
              f"veio {result_broken.n_failed}. Revisar a fixture. ***")
        ok = False
    else:
        print(f"OK -- fixture falha como esperado ({EXPECTED_N_FAILED_BROKEN} testes).")

    print("\n" + "=" * 70)
    print(f"2) Estado corrigido (aplicando {SOLUTION.name})")
    print("=" * 70)
    workdir_fixed = task.setup()
    fixed_content = SOLUTION.read_text(encoding="utf-8")
    task.write_source(workdir_fixed, SOURCE_REL_PATH, fixed_content)
    result_fixed = task.verify(workdir_fixed)
    print(result_fixed.summary)
    print(result_fixed.stdout)
    if not result_fixed.passed:
        print("*** FALHA DO CONTROL-CHECK: o fix certo deveria passar e nao passou. ***")
        ok = False
    else:
        print("OK -- com o fix certo, todos os testes passam.")

    print("\n" + "=" * 70)
    print("RESULTADO DO CONTROL-CHECK:", "PASSOU" if ok else "FALHOU")
    print("=" * 70)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
