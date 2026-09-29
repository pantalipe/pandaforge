"""
Backend contra o llama-server (via llama-swap) para o PandaForge.

Dois caminhos, deliberadamente expostos separadamente:

- complete(): endpoint nativo /completion do llama.cpp. E o unico que
  permite parar em n_predict, ler o campo `stop_type` (sinaliza se foi
  cortado pelo orcamento ou terminou naturalmente) e continuar a
  geracao a partir de um prefixo modificado (para o truque de injetar
  `</think>` manualmente). Usado pelas estrategias `think` e
  `iterative`.

- chat(): endpoint /v1/chat/completions (OpenAI-compatible), o mesmo
  que o pandagent.PandaClient usa hoje. Mais simples, sem controle de
  corte, mas ja devolve `usage` e `timings` -- confirmado
  empiricamente (ver probe_llama_server.py). Usado pela estrategia
  `no_think` como baseline direto comparavel ao resto do ecossistema.

Confirmado empiricamente neste hardware (Xeon E3-1230 v2, sem AVX2,
16GB RAM, llama-swap :8081, qwen3:4b):

- a primeira chamada apos o modelo ficar ocioso paga um custo de
  troca/carregamento de modelo que NADA tem a ver com prefill real
  (~40s para 16 tokens de prompt vs ~0.2s aquecido) -- por isso
  warm_up() existe e deve ser chamado, descartado, antes de medir
  qualquer coisa.
- prefill (`prompt_per_second`) roda mais rapido que decode
  (`predicted_per_second`) mesmo sem AVX2 -- nao e o gargalo que se
  supunha.
- `stop_type == "limit"` e o sinal correto e direto de que o
  orcamento (`n_predict`) cortou a geracao antes do fim natural.

Zero dependencias externas -- so stdlib (urllib), como o resto do
ecossistema.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any


DEFAULT_BASE_URL = "http://localhost:8081"
DEFAULT_MODEL = "qwen3:4b"


class BackendError(Exception):
    """Erro de comunicacao com o llama-server (HTTP ou rede)."""

    def __init__(self, message: str, status: int | None = None, body: str = ""):
        super().__init__(message)
        self.status = status
        self.body = body


@dataclass
class Generation:
    """
    Resultado normalizado de uma chamada de geracao, venha ela do
    /completion nativo ou do /v1/chat/completions.

    Campos que so existem em um dos dois caminhos ficam vazios/None
    no outro -- a estrategia que consome isso decide o que precisa.
    """

    content: str
    model: str = ""

    # Contagens de tokens (nomes do /completion nativo; chat() preenche
    # os equivalentes a partir de `usage`)
    tokens_predicted: int = 0     # tokens gerados nesta chamada
    tokens_evaluated: int = 0     # tokens do prompt processados (nao vieram do cache)
    tokens_cached: int = 0        # tokens do prompt reaproveitados do cache

    # Sinal de corte -- so existe de fato no /completion nativo. Valores
    # observados: "limit" (cortou no n_predict), "eos"/"word" (terminou
    # naturalmente). chat() preenche com finish_reason (ex: "stop").
    stop_type: str | None = None
    truncated: bool = False

    # Tempos brutos, direto do campo `timings` do backend (mesma forma
    # nos dois caminhos, confirmado empiricamente)
    prompt_ms: float = 0.0
    prompt_tokens_n: int = 0
    prompt_per_second: float = 0.0
    predicted_ms: float = 0.0
    predicted_per_second: float = 0.0

    wall_time_s: float = 0.0      # tempo de parede medido por nos (inclui rede)
    reasoning_content: str = ""   # so chat(): texto de pensamento separado (Qwen3.5+)
    raw: dict[str, Any] = field(default_factory=dict)  # resposta crua, p/ debug/auditoria

    @property
    def hit_budget_limit(self) -> bool:
        """True quando o /completion nativo cortou a geracao pelo n_predict."""
        return self.stop_type == "limit"


class LlamaServerBackend:
    """
    Cliente fino para um servidor llama-server (direto ou atras do
    llama-swap). Nao decide prompt nem estrategia -- so fala com o
    backend e devolve Generation normalizado.
    """

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        model: str = DEFAULT_MODEL,
        timeout_s: float = 900.0,
        seed: int | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_s = timeout_s
        # seed de amostragem enviada em toda geracao (None = aleatoria,
        # comportamento padrao do llama-server). Mude entre execucoes
        # (backend.seed = N) para medir variancia de forma reprodutivel.
        self.seed = seed

    # -----------------------------------------------------------
    # baixo nivel
    # -----------------------------------------------------------

    def _post(self, path: str, payload: dict) -> tuple[dict, float]:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self.base_url + path,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        t0 = time.time()
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            return body, time.time() - t0
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")
            raise BackendError(
                f"HTTP {e.code} em {path}: {detail[:500]}", status=e.code, body=detail
            ) from e
        except urllib.error.URLError as e:
            raise BackendError(f"servidor inacessivel em {path}: {e.reason}") from e

    def is_online(self) -> bool:
        try:
            req = urllib.request.Request(self.base_url + "/v1/models", method="GET")
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status == 200
        except Exception:
            return False

    def list_models(self) -> list[str]:
        req = urllib.request.Request(self.base_url + "/v1/models", method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return [m["id"] for m in data.get("data", [])]

    # -----------------------------------------------------------
    # aquecimento
    # -----------------------------------------------------------

    def warm_up(self, n_predict: int = 4) -> float:
        """
        Forca o llama-swap a carregar/trocar para self.model e descarta
        o resultado. Devolve o tempo de parede gasto -- isso E o custo
        de troca de modelo, medido separadamente do prefill/decode
        reais. Chame isso e descarte antes de medir qualquer
        experimento (confirmado empiricamente: ~40s frio vs ~0.2s
        aquecido para o mesmo prompt).
        """
        body, dt = self._post("/completion", {
            "model": self.model,
            "prompt": "Ok.",
            "n_predict": n_predict,
            "temperature": 0.0,
            "cache_prompt": True,
        })
        return dt

    # -----------------------------------------------------------
    # /completion nativo -- controle fino (budget, corte, continuacao)
    # -----------------------------------------------------------

    def _generation_from_completion(self, body: dict, wall_time_s: float) -> Generation:
        timings = body.get("timings", {})
        return Generation(
            content=body.get("content", ""),
            model=body.get("model", self.model),
            tokens_predicted=body.get("tokens_predicted", 0),
            tokens_evaluated=body.get("tokens_evaluated", 0),
            tokens_cached=body.get("tokens_cached", 0),
            stop_type=body.get("stop_type"),
            truncated=body.get("truncated", False),
            prompt_ms=timings.get("prompt_ms", 0.0),
            prompt_tokens_n=timings.get("prompt_n", 0),
            prompt_per_second=timings.get("prompt_per_second", 0.0),
            predicted_ms=timings.get("predicted_ms", 0.0),
            predicted_per_second=timings.get("predicted_per_second", 0.0),
            wall_time_s=wall_time_s,
            raw=body,
        )

    def complete(
        self,
        prompt: str,
        n_predict: int,
        temperature: float = 0.6,
        top_p: float = 0.95,
        cache_prompt: bool = True,
        stop: list[str] | None = None,
        extra: dict | None = None,
    ) -> Generation:
        """
        Chama /completion diretamente. `n_predict` e o orcamento desta
        chamada -- para thinking, e o orcamento de thinking (o modelo
        pode ou nao terminar o </think> dentro dele; verifique
        `stop_type`/`hit_budget_limit`).
        """
        payload = {
            "model": self.model,
            "prompt": prompt,
            "n_predict": n_predict,
            "temperature": temperature,
            "top_p": top_p,
            "cache_prompt": cache_prompt,
        }
        if self.seed is not None:
            payload["seed"] = self.seed
        if stop:
            payload["stop"] = stop
        if extra:
            payload.update(extra)
        body, dt = self._post("/completion", payload)
        return self._generation_from_completion(body, dt)

    def continue_after_budget(
        self,
        prompt: str,
        cut_generation: Generation,
        n_predict: int,
        close_tag: str = "\n</think>\n\n",
        **kwargs,
    ) -> Generation:
        """
        Costura o truque de orcamento de thinking em duas chamadas:
        pega o prompt original + o conteudo cortado (de uma chamada
        anterior que bateu no `n_predict`), injeta `close_tag` para
        forcar o fim do thinking, e continua a geracao a partir dai.
        `cache_prompt=True` (default de complete()) reaproveita o
        prefixo -- confirmado empiricamente: so os tokens novos
        (prompt + conteudo cortado + close_tag) sao reprocessados.
        """
        forced_prefix = prompt + cut_generation.content + close_tag
        return self.complete(forced_prefix, n_predict=n_predict, **kwargs)

    # -----------------------------------------------------------
    # /v1/chat/completions -- baseline comparavel ao pandagent
    # -----------------------------------------------------------

    def chat(
        self,
        messages: list[dict],
        max_tokens: int = 2048,
        temperature: float = 0.5,
        top_p: float = 0.9,
        extra: dict | None = None,
    ) -> Generation:
        """
        Chama /v1/chat/completions (o mesmo endpoint do
        pandagent.PandaClient.ask()). Nao ha `stop_type` nem controle
        de corte no meio do thinking aqui -- para isso, use complete().

        `extra` deixa passar campos extras do payload -- em particular
        `chat_template_kwargs: {"enable_thinking": False}`, necessario
        para desligar o pensamento em modelos Qwen3.5+ (confirmado
        empiricamente: o prefixo de texto "/no_think" do Qwen3 nao tem
        efeito aqui, e o llama-server separa o pensamento em
        `reasoning_content`, deixando `content` vazio se cortado no
        meio -- ver probe_qwen35_*.py).
        """
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "temperature": temperature,
            "top_p": top_p,
            "max_tokens": max_tokens,
        }
        if self.seed is not None:
            payload["seed"] = self.seed
        if extra:
            payload.update(extra)
        body, dt = self._post("/v1/chat/completions", payload)
        choice = (body.get("choices") or [{}])[0]
        message = choice.get("message", {})
        content = (message.get("content") or "").strip()
        reasoning_content = (message.get("reasoning_content") or "").strip()
        usage = body.get("usage", {})
        timings = body.get("timings", {})
        return Generation(
            content=content,
            model=body.get("model", self.model),
            tokens_predicted=usage.get("completion_tokens", 0),
            tokens_evaluated=usage.get("prompt_tokens", 0),
            tokens_cached=usage.get("prompt_tokens_details", {}).get("cached_tokens", 0),
            stop_type=choice.get("finish_reason"),
            prompt_ms=timings.get("prompt_ms", 0.0),
            prompt_tokens_n=timings.get("prompt_n", 0),
            prompt_per_second=timings.get("prompt_per_second", 0.0),
            predicted_ms=timings.get("predicted_ms", 0.0),
            predicted_per_second=timings.get("predicted_per_second", 0.0),
            wall_time_s=dt,
            reasoning_content=reasoning_content,
            raw=body,
        )
