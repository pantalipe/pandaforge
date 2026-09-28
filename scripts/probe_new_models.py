"""
Sondagem rapida de compatibilidade dos 3 modelos novos -- confirma se
o formato de prompt cru (<|im_start|>/<|im_end|>) usado por
think/iterative funciona em cada um antes de rodar a suite completa.
"""
import sys
sys.path.insert(0, "C:/Users/panta/pandaforge/src")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from pandaforge.backend.llama_server import LlamaServerBackend

PROMPT_TEXT = "Quanto e 17 * 23? Pense passo a passo antes de responder."
MODELS = ["qwen3.5:2b", "qwen3:1.7b", "deepseek-r1-distill-qwen:1.5b"]

for model in MODELS:
    print("\n" + "=" * 70)
    print(model)
    print("=" * 70)
    backend = LlamaServerBackend(model=model)
    warm = backend.warm_up()
    print(f"aquecimento: {warm:.2f}s")

    prompt = f"<|im_start|>user\n{PROMPT_TEXT}<|im_end|>\n<|im_start|>assistant\n"
    gen = backend.complete(prompt, n_predict=300, temperature=0.6)
    print(f"tokens={gen.tokens_predicted} stop_type={gen.stop_type!r} "
          f"tok/s={gen.predicted_per_second:.1f}")
    print(f"contem <think>? {'<think>' in gen.content}")
    print(f"contem '391' (resposta certa)? {'391' in gen.content}")
    print(f"conteudo (300 chars): {gen.content[:300]!r}")
