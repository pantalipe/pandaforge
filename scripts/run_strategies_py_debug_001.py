"""
Roda as 3 estrategias (no_think, think, iterative) numa tarefa da
task suite e imprime um relatorio comparativo.

O veredito de sucesso de cada estrategia vem SEMPRE de
task.verify(workdir) -- o pytest real rodando no estado final do
arquivo -- nunca de o agente "achar" que terminou.

Uso:
    python scripts/run_strategies_py_debug_001.py --task py_debug_002 --think-budget 1200
"""
import argparse
import sys

sys.path.insert(0, "C:/Users/panta/pandaforge/src")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from pandaforge.backend.llama_server import LlamaServerBackend  # noqa: E402
from pandaforge.tasks import PyDebugTask  # noqa: E402
from pandaforge.strategies import run_no_think, run_think, run_iterative  # noqa: E402
from pandaforge.metrics import record_episode  # noqa: E402

HYPOTHESIS = (
    "Um modelo pequeno com reasoning limitado, estado externo e ciclos "
    "iterativos pode resolver tarefas que o mesmo modelo, usando /no_think "
    "ou uma unica janela de reasoning, nao consegue -- dentro dos mesmos "
    "recursos computacionais."
)


def section(title):
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)


def report(ep):
    r = ep.final_task_result
    status = "PASSOU" if r.passed else f"FALHOU ({r.summary})"
    print(f"[{ep.strategy}] {status}")
    print(f"    tokens_predicted total = {ep.total_tokens}")
    print(f"    tempo total (parede)   = {ep.total_wall_s:.2f}s")
    print(f"    chamadas ao modelo     = {ep.n_calls}")
    print(f"    parse_ok               = {ep.parse_ok}")
    if not r.passed:
        print(f"    detalhe pytest:\n{r.stdout[-600:]}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--think-budget", type=int, default=800)
    ap.add_argument("--continue-budget", type=int, default=250)
    ap.add_argument("--iter-cycles", type=int, default=6)
    ap.add_argument("--edit-tool", choices=["write", "patch"], default="write",
                     help="mecanismo de edicao do iterative -- 'patch' testa H2")
    ap.add_argument("--protocol", choices=["structured", "simple"], default="structured",
                     help="protocolo de acao do iterative -- 'simple' e calibrado para modelos pequenos")
    ap.add_argument("--model", default="qwen3:4b")
    ap.add_argument("--task", default="py_debug_001")
    ap.add_argument("--only", default="abc",
                     help="quais estrategias rodar, ex.: 'bc' pula o no_think")
    args = ap.parse_args()

    backend = LlamaServerBackend(model=args.model)
    if not backend.is_online():
        print("Servidor offline -- verifique o llama-swap (panda llm health).")
        return

    section("Aquecimento (descartado)")
    print(f"custo de troca/carregamento: {backend.warm_up():.2f}s")

    task = PyDebugTask.load(args.task)
    episodes = []

    if "a" in args.only:
        section("A) NO_THINK")
        ep_a = run_no_think(backend, task, task.setup())
        report(ep_a)
        episodes.append(ep_a)
        record_episode(args.task, ep_a, args.model, config={}, hypothesis=HYPOTHESIS)

    if "b" in args.only:
        section(f"B) THINK (budget={args.think_budget})")
        ep_b = run_think(backend, task, task.setup(), think_budget=args.think_budget)
        report(ep_b)
        episodes.append(ep_b)
        record_episode(args.task, ep_b, args.model,
                        config={"think_budget": args.think_budget}, hypothesis=HYPOTHESIS)

    if "c" in args.only:
        section(f"C) ITERATIVE (protocol={args.protocol}, edit_tool={args.edit_tool}, "
                f"budget={args.think_budget}, continue={args.continue_budget}, "
                f"ciclos={args.iter_cycles})")
        ep_c = run_iterative(
            backend, task, task.setup(),
            think_budget=args.think_budget,
            continue_budget=args.continue_budget,
            max_cycles=args.iter_cycles,
            edit_tool=args.edit_tool,
            protocol=args.protocol,
        )
        report(ep_c)
        episodes.append(ep_c)
        record_episode(args.task, ep_c, args.model,
                        config={"think_budget": args.think_budget,
                                "continue_budget": args.continue_budget,
                                "max_cycles": args.iter_cycles,
                                "edit_tool": args.edit_tool,
                                "protocol": args.protocol},
                        hypothesis=HYPOTHESIS)

    section("RESUMO")
    print(f"{'estrategia':10s}  {'passou':7s}  {'tokens':>7s}  {'tempo(s)':>9s}  {'chamadas':>9s}")
    for ep in episodes:
        r = ep.final_task_result
        print(f"{ep.strategy:10s}  {str(r.passed):7s}  {ep.total_tokens:7d}  "
              f"{ep.total_wall_s:9.2f}  {ep.n_calls:9d}")


if __name__ == "__main__":
    main()
