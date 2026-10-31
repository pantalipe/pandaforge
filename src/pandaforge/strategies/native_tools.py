"""
Estrategia D (native_tools): mesma logica de ciclos do iterative.py --
estado externo compacto, uma acao por ciclo, tool executa de verdade,
resultado vira a observacao do proximo ciclo -- mas a decisao de qual
ferramenta usar e estruturada NATIVAMENTE pelo motor de inferencia
(tools=/tool_choice= via /v1/chat/completions), em vez de um
protocolo de texto customizado parseado pelo harness (tools/protocol.py).

Isola a variavel de H5 (docs/HYPOTHESES.md): mesmo modelo, mesmo
budget, mesmo conjunto de tools (edit_tool + decoy_tools) que
iterative.py -- so o MECANISMO de saida muda. Rodar H5 com o mesmo
edit_tool/decoy_tools/seed_files/max_cycles usados numa corrida de
iterative.py e comparar n_format_errors, n_decoy_calls, tokens e
tempo.

Pre-requisito confirmado empiricamente (ver panda-home-bot/docs/
pask-tool-calling-jinja-fix.md): o modelo servido precisa estar
rodando com --jinja no llama-swap, senao message.tool_calls nunca
vem populado -- a intencao de chamar a tool fica presa como texto
cru em reasoning_content, e cada ciclo contaria como
n_format_errors mesmo quando o modelo decidiu certo. qwen3:4b ja
tem --jinja habilitado (compartilhado com o /pask); os demais
modelos do PandaForge (qwen3.5:0.8b, qwen3.5:2b, qwen3:1.7b,
deepseek-r1-distill-qwen:1.5b) ainda nao -- precisam ser habilitados
em C:\\llama.cpp\\config.yaml antes de rodar H5 neles.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import List, Optional

from pandaforge.backend.llama_server import LlamaServerBackend, Generation
from pandaforge.tasks.base import PyDebugTask
from pandaforge.tools.fs import read_file, write_file, patch_file, ToolError
from pandaforge.tools.pyexec import run_tests
from pandaforge.tools.protocol import tool_schemas_for
from pandaforge.strategies.single_shot import EpisodeResult, _iter_source_files


def _auto_check_after_edit(task: PyDebugTask, workdir: Path, cycle: int, verbose: bool) -> bool:
    """Mesma logica de iterative.py::_auto_check_after_edit, sem depender
    de state_log (native_tools usa `messages`, nao uma lista de texto)."""
    result = task.verify(workdir)
    if result.passed:
        if verbose:
            print(f"  [ciclo {cycle}] verificacao automatica: TODOS OS TESTES PASSARAM "
                  f"-- encerrando o loop.", flush=True)
        return True
    return False


def run_native_tools(
    backend: LlamaServerBackend,
    task: PyDebugTask,
    workdir: Path,
    max_tokens: int = 500,
    max_cycles: int = 6,
    edit_tool: str = "patch",   # "write" ou "patch" -- mesmo vocabulario de iterative.py
    seed_files: List[str] | None = None,
    decoy_tools: List[str] | None = None,   # H4 x H5: mesmo menu de decoys que iterative.py
    disable_thinking: bool = False,
    verbose: bool = True,
) -> EpisodeResult:
    """
    ATENCAO (achado 2026-09-29, smoke test H5): diferente de
    iterative.py, chat() nao tem o truque de "corte no orcamento +
    continuacao forcada" que complete() tem -- se o modelo ainda
    estiver pensando quando `max_tokens` acabar, o ciclo INTEIRO se
    perde (finish_reason='length', sem tool_calls), sem chance de
    recuperar. Isso NAO e evidencia de que tool-calling nativo "erra
    mais" -- e uma assimetria de engenharia entre as duas estrategias
    que ainda falta resolver (TODO: continuacao equivalente para
    chat(), ou usar disable_thinking=True para remover a variavel de
    orcamento de pensamento da comparacao de H5).
    """
    tools = tool_schemas_for(edit_tool, decoy_tools)
    strategy_name = f"native_{edit_tool}"
    if decoy_tools:
        strategy_name += f"_decoys{len(decoy_tools)}"
    if disable_thinking:
        strategy_name += "_nothink"
    chat_extra = {"chat_template_kwargs": {"enable_thinking": False}} if disable_thinking else None

    generations: List[Generation] = []
    n_decoy_calls = 0
    n_format_errors = 0  # ciclo sem tool_calls -- equivalente ao ActionParseError do iterative

    if seed_files is None:
        seed_files = [p.relative_to(workdir).as_posix() for p in _iter_source_files(workdir)]

    seed_lines = []
    for seed_path in seed_files:
        try:
            obs = read_file(workdir, seed_path)
        except ToolError as e:
            obs = f"ERRO: {e}"
        seed_lines.append(f"Conteudo atual de {seed_path}:\n{obs}")
        if verbose:
            print(f"  [seed] read_file({seed_path}) automatico (nao conta como ciclo)",
                  flush=True)

    messages: list[dict] = [
        {
            "role": "system",
            "content": (
                task.objective
                + "\n\nVoce tem ferramentas disponiveis. Em cada resposta, "
                "chame EXATAMENTE uma ferramenta -- nao responda so com texto."
            ),
        },
        {"role": "user", "content": "\n\n".join(seed_lines) or "(nenhum arquivo lido ainda)"},
    ]

    for cycle in range(1, max_cycles + 1):
        cycle_t0 = time.time()
        gen = backend.chat(messages, max_tokens=max_tokens, tools=tools, tool_choice="auto",
                           extra=chat_extra)
        generations.append(gen)
        if verbose:
            print(f"  [ciclo {cycle}] chamada: {gen.wall_time_s:.1f}s, "
                  f"{gen.tokens_predicted} tok, finish_reason={gen.stop_type!r}", flush=True)

        if not gen.tool_calls:
            n_format_errors += 1
            if verbose:
                print(f"  [ciclo {cycle}] SEM tool_calls -- resposta ignorada "
                      f"(ciclo total: {time.time() - cycle_t0:.1f}s)", flush=True)
            messages.append({
                "role": "user",
                "content": "Voce precisa chamar uma das ferramentas disponiveis -- "
                            "nao responda so com texto.",
            })
            continue

        call = gen.tool_calls[0]  # so a primeira -- mesma regra de "uma acao por ciclo"
        fn = call.get("function", {})
        tool_name = fn.get("name", "")
        try:
            args = json.loads(fn.get("arguments") or "{}")
        except json.JSONDecodeError:
            args = {}
        path = args.get("path")

        # Eco somente da chamada executada: cada id anunciado no historico
        # precisa de resposta. Generation preserva todas as propostas para
        # auditoria, inclusive as extras que nao executamos neste ciclo.
        messages.append({
            "role": "assistant",
            "content": gen.content or None,
            "tool_calls": [call],
        })

        if verbose:
            print(f"  [ciclo {cycle}] acao: {tool_name}"
                  + (f" {path}" if path else "")
                  + f" (ciclo total: {time.time() - cycle_t0:.1f}s)", flush=True)

        finished = False
        if tool_name == "read_file":
            try:
                obs = read_file(workdir, path)
            except ToolError as e:
                obs = f"ERRO: {e}"

        elif tool_name == "write_file":
            try:
                write_file(workdir, path, args.get("content") or "")
                obs = "arquivo escrito com sucesso."
            except ToolError as e:
                obs = f"ERRO: {e}"
            if not obs.startswith("ERRO"):
                finished = _auto_check_after_edit(task, workdir, cycle, verbose)

        elif tool_name == "patch_file":
            try:
                patch_file(workdir, path, args.get("old") or "", args.get("content") or "")
                obs = "trecho substituido com sucesso."
            except ToolError as e:
                obs = f"ERRO: {e}"
            if not obs.startswith("ERRO"):
                finished = _auto_check_after_edit(task, workdir, cycle, verbose)

        elif tool_name == "run_tests":
            obs = run_tests(workdir)

        elif tool_name == "done":
            messages.append({
                "role": "tool", "tool_call_id": call.get("id", ""), "content": "ok."
            })
            state_msg = f"[ciclo {cycle}] done() -- agente declarou que terminou."
            if verbose:
                print(f"  {state_msg}", flush=True)
            break

        else:
            # decoy tool (H4 x H5): existe no menu, o modelo chamou de
            # verdade (tool_calls valido, so a ferramenta e inutil),
            # mas nao faz nada -- custa um ciclo real, igual custaria
            # no /pask escolher a tool errada.
            n_decoy_calls += 1
            obs = "ERRO: ferramenta nao disponivel para esta tarefa."
            if verbose:
                print(f"  [ciclo {cycle}] DECOY escolhida: {tool_name} -> {obs}", flush=True)

        messages.append({"role": "tool", "tool_call_id": call.get("id", ""), "content": obs})
        if finished:
            break

    result = task.verify(workdir)
    return EpisodeResult(
        strategy=strategy_name,
        final_task_result=result,
        generations=generations,
        extracted_code=None,
        parse_ok=(n_format_errors == 0),
        n_decoy_calls=n_decoy_calls,
        n_format_errors=n_format_errors,
    )
