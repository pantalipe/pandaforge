"""
Roda as 3 estrategias (no_think, think, iterative) numa tarefa da
task suite e imprime um relatorio comparativo -- opcionalmente com
varias sementes por celula, para medir taxa de sucesso em vez de um
unico resultado binario (ver docs/NEGATIVE_RESULTS.md: uma execucao
so nao sustenta comparacao entre modelos).

O veredito de sucesso de cada estrategia vem SEMPRE de
task.verify(workdir) -- o pytest real rodando no estado final do
arquivo -- nunca de o agente "achar" que terminou.

Uso:
    python scripts/run_strategies_py_debug_001.py --task py_debug_002 --think-budget 1200
    python scripts/run_strategies_py_debug_001.py --model qwen3.5:2b --seeds 5 --only ac
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


def report(ep, seed=None):
    r = ep.final_task_result
    status = "PASSOU" if r.passed else f"FALHOU ({r.summary})"
    seed_note = f" [seed={seed}]" if seed is not None else ""
    print(f"[{ep.strategy}]{seed_note} {status}  "
          f"tokens={ep.total_tokens} tempo={ep.total_wall_s:.2f}s "
          f"chamadas={ep.n_calls} parse_ok={ep.parse_ok}")
    if not r.passed:
        print(f"    detalhe pytest (ultimas linhas): {r.stdout.strip().splitlines()[-1] if r.stdout.strip() else ''}")


def run_cell(strategy_label, run_fn, backend, task, args, config, extra_config=None):
    """
    Roda uma estrategia args.seeds vezes (seeds base_seed..base_seed+N-1),
    registra cada episodio e devolve a lista de EpisodeResult.
    """
    episodes = []
    for i in range(args.seeds):
        seed = args.base_seed + i
        backend.seed = seed
        ep = run_fn()
        report(ep, seed=seed if args.seeds > 1 else None)
        full_config = dict(config)
        full_config["seed"] = seed
        if extra_config:
            full_config.update(extra_config)
        record_episode(args.task, ep, args.model, config=full_config, hypothesis=HYPOTHESIS)
        episodes.append(ep)
    return episodes


def aggregate(strategy_label, episodes):
    n = len(episodes)
    n_passed = sum(1 for ep in episodes if ep.final_task_result.passed)
    avg_tokens = sum(ep.total_tokens for ep in episodes) / n
    avg_time = sum(ep.total_wall_s for ep in episodes) / n
    return {
        "strategy": strategy_label,
        "n": n,
        "n_passed": n_passed,
        "rate": n_passed / n,
        "avg_tokens": avg_tokens,
        "avg_time": avg_time,
    }


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
    ap.add_argument("--seeds", type=int, default=1,
                     help="quantas vezes rodar cada estrategia (com seeds diferentes)")
    ap.add_argument("--base-seed", type=int, default=0)
    args = ap.parse_args()

    backend = LlamaServerBackend(model=args.model)
    if not backend.is_online():
        print("Servidor offline -- verifique o llama-swap (panda llm health).")
        return

    section("Aquecimento (descartado)")
    print(f"custo de troca/carregamento: {backend.warm_up():.2f}s")

    task = PyDebugTask.load(args.task)
    all_aggregates = []

    if "a" in args.only:
        section(f"A) NO_THINK ({args.seeds} semente(s))")
        eps = run_cell("no_think", lambda: run_no_think(backend, task, task.setup()),
                        backend, task, args, config={})
        all_aggregates.append(aggregate("no_think", eps))

    if "b" in args.only:
        section(f"B) THINK (budget={args.think_budget}, {args.seeds} semente(s))")
        eps = run_cell(
            "think",
            lambda: run_think(backend, task, task.setup(), think_budget=args.think_budget),
            backend, task, args, config={"think_budget": args.think_budget},
        )
        all_aggregates.append(aggregate("think", eps))

    if "c" in args.only:
        section(f"C) ITERATIVE (protocol={args.protocol}, edit_tool={args.edit_tool}, "
                f"budget={args.think_budget}, continue={args.continue_budget}, "
                f"ciclos={args.iter_cycles}, {args.seeds} semente(s))")
        eps = run_cell(
            "iterative",
            lambda: run_iterative(
                backend, task, task.setup(),
                think_budget=args.think_budget,
                continue_budget=args.continue_budget,
                max_cycles=args.iter_cycles,
                edit_tool=args.edit_tool,
                protocol=args.protocol,
            ),
            backend, task, args,
            config={"think_budget": args.think_budget,
                    "continue_budget": args.continue_budget,
                    "max_cycles": args.iter_cycles,
                    "edit_tool": args.edit_tool,
                    "protocol": args.protocol},
        )
        all_aggregates.append(aggregate(eps[0].strategy if eps else "iterative", eps))

    section("RESUMO")
    print(f"{'estrategia':20s}  {'sucesso':>10s}  {'avg tokens':>10s}  {'avg tempo(s)':>12s}")
    for agg in all_aggregates:
        print(f"{agg['strategy']:20s}  {agg['n_passed']}/{agg['n']:<8d}  "
              f"{agg['avg_tokens']:10.0f}  {agg['avg_time']:12.2f}")


if __name__ == "__main__":
    main()
