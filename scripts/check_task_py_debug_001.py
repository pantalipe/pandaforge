"""
Control-check da tarefa py_debug_001 -- SEM LLM nenhum envolvido.

Prova duas coisas antes de gastar um unico token de inferencia:
  1) a fixture, como esta, FALHA no pytest (o bug e real).
  2) aplicando o fix certo, o MESMO verificador PASSA.

Se qualquer uma dessas duas checagens falhar, a tarefa esta mal
construida e precisa ser corrigida antes de entrar na task suite --
principio do projeto: nao assumir que uma tarefa mede o que deveria
sem medir isso primeiro.
"""
import sys
sys.path.insert(0, "C:/Users/panta/pandaforge/src")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from pathlib import Path
from pandaforge.tasks import PyDebugTask

SOLUTION = Path("C:/Users/panta/pandaforge/src/pandaforge/tasks/"
                 "suite/py_debug_001/solution/orders_fixed.py")


def main():
    task = PyDebugTask.load("py_debug_001")
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
    elif result_broken.n_failed != 1:
        print(f"*** AVISO: esperava exatamente 1 teste falhando, "
              f"veio {result_broken.n_failed}. Revisar a fixture. ***")
        ok = False
    else:
        print("OK -- fixture falha como esperado (1 teste, o do desconto).")

    print("\n" + "=" * 70)
    print("2) Estado corrigido (aplicando solution/orders_fixed.py)")
    print("=" * 70)
    workdir_fixed = task.setup()
    fixed_content = SOLUTION.read_text(encoding="utf-8")
    task.write_source(workdir_fixed, "src/orders.py", fixed_content)
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
