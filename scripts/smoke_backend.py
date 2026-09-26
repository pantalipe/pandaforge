"""
Smoke test manual do LlamaServerBackend -- compara as 3 estrategias
(no_think, think, iterative) na mesma tarefa, com o orcamento de
thinking ajustavel por linha de comando.

Uso:
    python scripts/smoke_backend.py --task "Quanto e 17 * 23?" --think-budget 300

Rode repetidas vezes variando --think-budget para calibrar o valor
antes de fixar qualquer coisa na task suite.
"""
import argparse
import sys
sys.path.insert(0, "C:/Users/panta/pandaforge/src")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from pandaforge.backend.llama_server import LlamaServerBackend  # noqa: E402


def section(title):
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)


def report(label, gen, extra_note=""):
    print(f"[{label}] wall={gen.wall_time_s:.2f}s  "
          f"tokens_predicted={gen.tokens_predicted}  "
          f"tokens_cached={gen.tokens_cached}  "
          f"prompt_tok/s={gen.prompt_per_second:.2f}  "
          f"decode_tok/s={gen.predicted_per_second:.2f}  "
          f"stop_type={gen.stop_type!r}  "
          f"hit_budget_limit={gen.hit_budget_limit}{extra_note}")
    print(f"    conteudo: {gen.content!r}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--task", default="Quanto e 17 * 23? Pense passo a passo.")
    ap.add_argument("--think-budget", type=int, default=300,
                     help="n_predict do orcamento de thinking (think/iterative)")
    ap.add_argument("--continue-budget", type=int, default=128,
                     help="n_predict da continuacao apos cortar (iterative)")
    ap.add_argument("--model", default="qwen3:4b")
    args = ap.parse_args()

    backend = LlamaServerBackend(model=args.model)

    if not backend.is_online():
        print("Servidor offline -- verifique o llama-swap (panda llm health).")
        return

    section("Aquecimento (descartado)")
    warm_s = backend.warm_up()
    print(f"custo de troca/carregamento de modelo: {warm_s:.2f}s")

    prompt = (
        "<|im_start|>user\n" + args.task + "<|im_end|>\n<|im_start|>assistant\n"
    )

    section("A) NO_THINK -- /v1/chat/completions, baseline do ecossistema")
    gen_a = backend.chat(
        messages=[{"role": "user", "content": "/no_think " + args.task}],
        max_tokens=512,
        temperature=0.2,
    )
    report("no_think", gen_a)

    section(f"B) THINK -- /completion, budget={args.think_budget}, sem continuar")
    gen_b = backend.complete(prompt, n_predict=args.think_budget)
    report("think", gen_b,
           extra_note="  <-- se hit_budget_limit=True, o pensamento foi cortado no meio")

    section(f"C) ITERATIVE -- corta em {args.think_budget}, injeta </think>, "
            f"continua com budget={args.continue_budget}")
    gen_c1 = backend.complete(prompt, n_predict=args.think_budget)
    report("iterative (ciclo 1, pensando)", gen_c1)
    gen_c2 = backend.continue_after_budget(
        prompt, gen_c1, n_predict=args.continue_budget
    )
    report("iterative (ciclo 2, apos </think> forcado)", gen_c2)

    section("RESUMO")
    print(f"no_think:   tokens_predicted={gen_a.tokens_predicted:4d}  "
          f"wall={gen_a.wall_time_s:6.2f}s")
    print(f"think:      tokens_predicted={gen_b.tokens_predicted:4d}  "
          f"wall={gen_b.wall_time_s:6.2f}s  cortou={gen_b.hit_budget_limit}")
    total_iter_tokens = gen_c1.tokens_predicted + gen_c2.tokens_predicted
    total_iter_wall = gen_c1.wall_time_s + gen_c2.wall_time_s
    print(f"iterative:  tokens_predicted={total_iter_tokens:4d}  "
          f"wall={total_iter_wall:6.2f}s  (2 chamadas)")


if __name__ == "__main__":
    main()
