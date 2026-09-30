"""
Bateria de comparacao H4 x H5 (docs/HYPOTHESES.md) -- roda iterative.py
(protocolo de texto <action>) e native_tools.py (tool-calling nativo)
com e sem decoys, varias sementes, e grava tudo via
metrics/recorder.py em results/<task>.jsonl.

O veredito de sucesso de cada celula vem SEMPRE de task.verify(workdir)
(pytest real), nunca da auto-declaracao do agente.

ATENCAO (ver docs/HYPOTHESES.md, H5): native_tools.py so roda de forma
confiavel com disable_thinking=True -- chat() nao tem o truque de
continuacao-apos-corte que complete() tem, entao com thinking ligado o
modelo pode gastar o orcamento inteiro pensando e nunca emitir uma
tool_call. Por isso a comparacao aqui e "iterative com thinking padrao"
vs "native SEM thinking" -- nao e mecanismo isolado de tudo mais, e
essa mistura fica registrada no config de cada episodio.

Uso:
    python scripts/run_h4_h5_battery.py
    python scripts/run_h4_h5_battery.py --task py_debug_002 --seeds 5
    python scripts/run_h4_h5_battery.py --only iterative_nodecoy,native_decoys
"""
import argparse
import sys
import time

sys.path.insert(0, "C:/Users/panta/pandaforge/src")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from pandaforge.backend.llama_server import LlamaServerBackend  # noqa: E402
from pandaforge.tasks import PyDebugTask  # noqa: E402
from pandaforge.strategies import run_iterative, run_native_tools  # noqa: E402
from pandaforge.metrics import record_episode  # noqa: E402

HYPOTHESIS = "H4xH5-battery-2026-09-30"
DECOYS = ["run_lint", "git_blame", "search_docs"]

# (label, kind, kwargs) -- kind decide qual run_fn e usada
CELLS = [
    ("iterative_nodecoy", "iterative", dict(edit_tool="patch", protocol="structured", decoy_tools=None)),
    ("iterative_decoys3", "iterative", dict(edit_tool="patch", protocol="structured", decoy_tools=DECOYS)),
    ("native_nothink_nodecoy", "native", dict(edit_tool="patch", decoy_tools=None, disable_thinking=True)),
    ("native_nothink_decoys3", "native", dict(edit_tool="patch", decoy_tools=DECOYS, disable_thinking=True)),
]


def section(title):
    print("\n" + "=" * 70, flush=True)
    print(title, flush=True)
    print("=" * 70, flush=True)


def report(label, ep, seed, dt):
    r = ep.final_task_result
    status = "PASSOU" if r.passed else f"FALHOU ({r.summary})"
    print(f"[{label}] seed={seed} {status}  "
          f"tokens={ep.total_tokens} wall={dt:.1f}s "
          f"n_decoy_calls={ep.n_decoy_calls} n_format_errors={ep.n_format_errors}",
          flush=True)


def aggregate(label, episodes_and_times):
    n = len(episodes_and_times)
    n_passed = sum(1 for ep, _ in episodes_and_times if ep.final_task_result.passed)
    avg_tokens = sum(ep.total_tokens for ep, _ in episodes_and_times) / n
    avg_wall = sum(dt for _, dt in episodes_and_times) / n
    avg_decoys = sum(ep.n_decoy_calls for ep, _ in episodes_and_times) / n
    avg_fmt_err = sum(ep.n_format_errors for ep, _ in episodes_and_times) / n
    return {
        "label": label, "n": n, "n_passed": n_passed, "rate": n_passed / n,
        "avg_tokens": avg_tokens, "avg_wall": avg_wall,
        "avg_decoys": avg_decoys, "avg_fmt_err": avg_fmt_err,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="qwen3:4b")
    ap.add_argument("--task", default="py_debug_001")
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--base-seed", type=int, default=0)
    ap.add_argument("--max-cycles", type=int, default=4)
    ap.add_argument("--only", default="",
                     help="lista separada por virgula de labels de CELLS a rodar; vazio = todas")
    args = ap.parse_args()

    backend = LlamaServerBackend(model=args.model)
    if not backend.is_online():
        print("Servidor offline -- verifique o llama-swap (panda llm health).")
        return

    section("Aquecimento (descartado)")
    print(f"custo de troca/carregamento: {backend.warm_up():.2f}s", flush=True)

    cells = CELLS
    if args.only:
        wanted = set(args.only.split(","))
        cells = [c for c in CELLS if c[0] in wanted]

    task_name = args.task
    all_aggregates = []
    t_battery0 = time.time()
    total_runs = len(cells) * args.seeds
    done = 0

    for label, kind, kwargs in cells:
        section(f"{label}  (kind={kind}, {args.seeds} semente(s), max_cycles={args.max_cycles})")
        episodes_and_times = []
        for i in range(args.seeds):
            seed = args.base_seed + i
            backend.seed = seed
            task = PyDebugTask.load(task_name)
            workdir = task.setup()
            t0 = time.time()
            if kind == "iterative":
                ep = run_iterative(backend, task, workdir, max_cycles=args.max_cycles,
                                    verbose=False, **kwargs)
            else:
                ep = run_native_tools(backend, task, workdir, max_cycles=args.max_cycles,
                                      verbose=False, **kwargs)
            dt = time.time() - t0
            done += 1
            report(label, ep, seed, dt)
            print(f"    [{done}/{total_runs} rodadas, {time.time()-t_battery0:.0f}s decorridos]",
                  flush=True)
            full_config = dict(kwargs)
            full_config["seed"] = seed
            full_config["max_cycles"] = args.max_cycles
            full_config["cell_label"] = label
            record_episode(task_name, ep, args.model, config=full_config, hypothesis=HYPOTHESIS)
            episodes_and_times.append((ep, dt))
        all_aggregates.append(aggregate(label, episodes_and_times))

    section("RESUMO")
    print(f"{'celula':26s}  {'sucesso':>10s}  {'avg tokens':>10s}  {'avg wall(s)':>11s}  "
          f"{'avg decoys':>10s}  {'avg fmt_err':>11s}", flush=True)
    for agg in all_aggregates:
        print(f"{agg['label']:26s}  {agg['n_passed']}/{agg['n']:<8d}  "
              f"{agg['avg_tokens']:10.0f}  {agg['avg_wall']:11.1f}  "
              f"{agg['avg_decoys']:10.2f}  {agg['avg_fmt_err']:11.2f}", flush=True)
    print(f"\nTOTAL: {time.time()-t_battery0:.0f}s para {total_runs} rodadas", flush=True)


if __name__ == "__main__":
    main()
