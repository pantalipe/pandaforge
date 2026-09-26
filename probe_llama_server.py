"""
Sondagem empirica do llama-server (via llama-swap, :8081) para o PandaForge.

Objetivo: confirmar, sem suposicoes, quais campos o backend realmente
devolve -- usage/timings no /v1/chat/completions, e o comportamento do
endpoint nativo /completion (que permite orcamento de thinking via
n_predict + injecao de </think>).

Nao depende de nada alem da stdlib.
"""
import json
import time
import urllib.request
import urllib.error

BASE = "http://localhost:8081"


def post(path, payload, timeout=120):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        BASE + path, data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        return body, time.time() - t0
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")
        print(f"   *** HTTP {e.code} em {path}: {detail[:500]} ***")
        return None, time.time() - t0


def section(title):
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)


def dump_keys(label, obj, skip=("content", "text")):
    print(f"-- {label}: top-level keys = {sorted(obj.keys())}")
    for k, v in obj.items():
        if k in skip:
            continue
        if isinstance(v, (dict, list)):
            print(f"   {k} = {json.dumps(v)[:300]}")
        else:
            print(f"   {k} = {v!r}")


# ---------------------------------------------------------------------
# Teste 1: /v1/chat/completions (o que o pandagent usa hoje) -- existe
# 'usage'? Com que granularidade?
# ---------------------------------------------------------------------
section("TESTE 1: /v1/chat/completions -- usage/timings")
body, dt = post("/v1/chat/completions", {
    "model": "qwen3:4b",
    "messages": [{"role": "user", "content": "/no_think Diga apenas: pong"}],
    "max_tokens": 16,
    "temperature": 0,
    "stream": False,
})
print(f"tempo de parede: {dt:.2f}s")
dump_keys("resposta", body)
if "usage" in body:
    dump_keys("usage", body["usage"])
else:
    print("   *** campo 'usage' AUSENTE ***")


# ---------------------------------------------------------------------
# Teste 2: /completion nativo do llama.cpp -- thinking LIGADO, sem
# cortar. Ve-se o campo 'timings' (prefill vs decode) e 'tokens_predicted'.
# ---------------------------------------------------------------------
section("TESTE 2: /completion nativo -- thinking ligado, timings")
prompt2 = (
    "<|im_start|>user\n"
    "Quanto e 17 * 23? Pense passo a passo antes de responder."
    "<|im_end|>\n<|im_start|>assistant\n"
)
body2, dt2 = post("/completion", {
    "model": "qwen3:4b",
    "prompt": prompt2,
    "n_predict": 300,
    "temperature": 0.6,
    "top_p": 0.95,
    "cache_prompt": True,
})
print(f"tempo de parede: {dt2:.2f}s")
if body2 is not None:
    dump_keys("resposta", body2)
    print(f"   len(content) = {len(body2.get('content', ''))} chars")
    print(f"   contem </think>? {'</think>' in body2.get('content', '')}")
    if "timings" in body2:
        dump_keys("timings", body2["timings"])
    else:
        print("   *** campo 'timings' AUSENTE ***")


# ---------------------------------------------------------------------
# Teste 3: orcamento de thinking curto o suficiente para CORTAR o
# raciocinio no meio -- e o que sinaliza que foi cortado?
# ---------------------------------------------------------------------
section("TESTE 3: /completion -- n_predict baixo, deve cortar o thinking")
body3, dt3 = post("/completion", {
    "model": "qwen3:4b",
    "prompt": prompt2,
    "n_predict": 40,   # bem menor que o necessario p/ terminar o raciocinio
    "temperature": 0.6,
    "top_p": 0.95,
    "cache_prompt": True,
})
print(f"tempo de parede: {dt3:.2f}s")
content3 = ""
if body3 is not None:
    dump_keys("resposta", body3)
    content3 = body3.get("content", "")
    print(f"   conteudo bruto: {content3!r}")
    print(f"   contem </think>? {'</think>' in content3}")
    for flag in ("stopped_limit", "stopped_eos", "truncated", "stop_type"):
        if flag in body3:
            print(f"   {flag} = {body3[flag]}")

# ---------------------------------------------------------------------
# Teste 4: apos o corte, injetar </think> manualmente e continuar a
# geracao a partir do prefixo -- valida a tecnica de orcamento de
# thinking via duas chamadas (cache_prompt evita reprocessar tudo).
# ---------------------------------------------------------------------
section("TESTE 4: continuar apos injetar </think> manualmente")
forced_prefix = prompt2 + content3 + "\n</think>\n\n"
body4, dt4 = post("/completion", {
    "model": "qwen3:4b",
    "prompt": forced_prefix,
    "n_predict": 64,
    "temperature": 0.6,
    "top_p": 0.95,
    "cache_prompt": True,
})
print(f"tempo de parede: {dt4:.2f}s")
if body4 is not None:
    dump_keys("resposta", body4)
    print(f"   conteudo final: {body4.get('content', '')!r}")
    if "timings" in body4:
        dump_keys("timings (chamada 2)", body4["timings"])

section("FIM DA SONDAGEM")
