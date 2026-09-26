"""
Sondagem de compatibilidade: qwen3.5:0.8b nao usa o soft-switch
/think e /no_think do Qwen3 -- thinking e controlado via parametro de
API (enable_thinking). Isso pode quebrar as estrategias think/iterative,
que constroem o prompt cru via /completion esperando que o modelo
comece a pensar sozinho a partir de um turno de assistente vazio.

Testa 3 caminhos:
  1) /completion cru (o que think/iterative usam hoje) -- pensa sozinho?
  2) /v1/chat/completions simples -- confirma modo padrao (non-thinking)
  3) /v1/chat/completions com enable_thinking=True no extra_body -- o
     llama-server local respeita esse parametro?
"""
import json
import sys
import urllib.request

sys.path.insert(0, "C:/Users/panta/pandaforge/src")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from pandaforge.backend.llama_server import LlamaServerBackend

MODEL = "qwen3.5:0.8b"
backend = LlamaServerBackend(model=MODEL)

print("aquecendo...")
print(f"custo de troca/carregamento: {backend.warm_up():.2f}s")

PROMPT_TEXT = "Quanto e 17 * 23? Pense passo a passo antes de responder."

print("\n=== 1) /completion cru (formato usado por think/iterative) ===")
prompt = f"<|im_start|>user\n{PROMPT_TEXT}<|im_end|>\n<|im_start|>assistant\n"
gen = backend.complete(prompt, n_predict=300, temperature=0.6)
print(f"tokens={gen.tokens_predicted} stop_type={gen.stop_type!r}")
print(f"contem <think>? {'<think>' in gen.content}")
print(f"conteudo: {gen.content[:400]!r}")

print("\n=== 2) /v1/chat/completions, sem enable_thinking (padrao) ===")
gen2 = backend.chat(messages=[{"role": "user", "content": PROMPT_TEXT}], max_tokens=300)
print(f"tokens={gen2.tokens_predicted}")
print(f"contem <think>? {'<think>' in gen2.content}")
print(f"conteudo: {gen2.content[:400]!r}")

print("\n=== 3) /v1/chat/completions com enable_thinking=True ===")
payload = {
    "model": MODEL,
    "messages": [{"role": "user", "content": PROMPT_TEXT}],
    "max_tokens": 300,
    "temperature": 1.0,
    "top_p": 0.95,
    "extra_body": {"enable_thinking": True},
    "chat_template_kwargs": {"enable_thinking": True},
}
req = urllib.request.Request(
    "http://localhost:8081/v1/chat/completions",
    data=json.dumps(payload).encode("utf-8"),
    headers={"Content-Type": "application/json"},
    method="POST",
)
try:
    with urllib.request.urlopen(req, timeout=120) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    content = body.get("choices", [{}])[0].get("message", {}).get("content", "")
    print(f"contem <think>? {'<think>' in content}")
    print(f"conteudo: {content[:400]!r}")
except Exception as e:
    print(f"erro: {e}")
