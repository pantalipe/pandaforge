"""
Estrategia C (iterative): estado externo compacto + loop curto de
ferramentas, em vez de mandar a tarefa inteira numa unica chamada.

Cada ciclo:
  1. o modelo recebe o objetivo + as ultimas observacoes (nao o
     historico inteiro -- e a variante "estado + ultimas observacoes"
     da lista de estrategias de compressao original);
  2. decide UMA acao (read_file / run_tests / write_file|patch_file / done);
  3. a ferramenta executa de verdade;
  4. o resultado vira a observacao do proximo ciclo.

O orcamento (think_budget) e por ciclo, nao pela tarefa inteira -- e
essa e a aposta central da hipotese: ciclos curtos, repetidos, em vez
de uma unica janela de raciocinio grande.

`edit_tool` escolhe write_file (reescreve o arquivo inteiro -- o
mecanismo original, que causou a regressao documentada em
docs/NEGATIVE_RESULTS.md) ou patch_file (edicao cirurgica -- testa H2
em docs/HYPOTHESES.md). So uma das duas fica disponivel por execucao,
pra isolar a variavel.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import List

from pandaforge.backend.llama_server import LlamaServerBackend
from pandaforge.tasks.base import PyDebugTask
from pandaforge.tools.fs import read_file, write_file, patch_file, ToolError
from pandaforge.tools.pyexec import run_tests
from pandaforge.tools.protocol import (
    parse_action,
    ActionParseError,
    TOOL_INSTRUCTIONS_WRITE,
    TOOL_INSTRUCTIONS_PATCH,
)
from pandaforge.strategies.prompts import TASK_OBJECTIVE
from pandaforge.strategies.single_shot import EpisodeResult


def _build_cycle_prompt(state_log: List[str], instructions: str) -> str:
    recent = "\n\n".join(state_log[-6:])
    body = (
        TASK_OBJECTIVE
        + "\n\n" + instructions
        + "\n\nHistorico recente (mais recente por ultimo):\n"
        + (recent or "(inicio -- nenhuma acao executada ainda)")
        + "\n\nPense brevemente sobre o proximo passo e emita UMA acao."
    )
    return f"<|im_start|>user\n{body}<|im_end|>\n<|im_start|>assistant\n"


def run_iterative(
    backend: LlamaServerBackend,
    task: PyDebugTask,
    workdir: Path,
    think_budget: int = 500,
    continue_budget: int = 250,
    max_cycles: int = 6,
    edit_tool: str = "write",   # "write" ou "patch" -- ver docstring/H2
    seed_files: List[str] | None = None,
    verbose: bool = True,
) -> EpisodeResult:
    if edit_tool not in ("write", "patch"):
        raise ValueError(f"edit_tool invalido: {edit_tool!r} (use 'write' ou 'patch')")
    instructions = TOOL_INSTRUCTIONS_PATCH if edit_tool == "patch" else TOOL_INSTRUCTIONS_WRITE

    generations = []
    state_log: List[str] = []
    all_cycles_parsed = True

    # Grounding automatico: o modelo NAO decide se le o arquivo antes de
    # editar -- descobrimos (ver docs/NEGATIVE_RESULTS.md) que ele pode
    # simplesmente nao ler e alucinar o conteudo. Entao o(s) arquivo(s)
    # relevante(s) entram no estado ANTES do ciclo 1, sem custar uma
    # chamada ao modelo.
    for seed_path in (seed_files or []):
        try:
            obs = read_file(workdir, seed_path)
        except ToolError as e:
            obs = f"ERRO: {e}"
        state_log.append(f"[seed] read_file({seed_path}) ->\n{obs}")
        if verbose:
            print(f"  [seed] read_file({seed_path}) automatico (nao conta como ciclo)",
                  flush=True)

    for cycle in range(1, max_cycles + 1):
        cycle_t0 = time.time()
        prompt = _build_cycle_prompt(state_log, instructions)
        gen = backend.complete(prompt, n_predict=think_budget, temperature=0.6)
        generations.append(gen)
        text = gen.content
        if verbose:
            print(f"  [ciclo {cycle}] chamada 1: {gen.wall_time_s:.1f}s, "
                  f"{gen.tokens_predicted} tok, stop_type={gen.stop_type!r}",
                  flush=True)

        if gen.hit_budget_limit and "</action>" not in text:
            gen2 = backend.continue_after_budget(
                prompt, gen, n_predict=continue_budget, close_tag="\n</action>\n"
            )
            generations.append(gen2)
            text = text + gen2.content
            if verbose:
                print(f"  [ciclo {cycle}] chamada 2 (continuacao): {gen2.wall_time_s:.1f}s, "
                      f"{gen2.tokens_predicted} tok, stop_type={gen2.stop_type!r}",
                      flush=True)

        try:
            action = parse_action(text)
        except ActionParseError as e:
            all_cycles_parsed = False
            state_log.append(
                f"[ciclo {cycle}] ERRO DE FORMATO: {e}. Lembre-se: termine "
                f"com exatamente um bloco <action>...</action>."
            )
            if verbose:
                print(f"  [ciclo {cycle}] ERRO DE FORMATO: {e} "
                      f"(ciclo total: {time.time() - cycle_t0:.1f}s)", flush=True)
            continue

        if verbose:
            print(f"  [ciclo {cycle}] acao: {action.tool}"
                  + (f" {action.path}" if action.path else "")
                  + f" (ciclo total: {time.time() - cycle_t0:.1f}s)", flush=True)

        if action.tool == "read_file":
            try:
                obs = read_file(workdir, action.path)
            except ToolError as e:
                obs = f"ERRO: {e}"
            state_log.append(f"[ciclo {cycle}] read_file({action.path}) ->\n{obs}")

        elif action.tool == "write_file":
            try:
                write_file(workdir, action.path, action.content or "")
                obs = "arquivo escrito com sucesso."
            except ToolError as e:
                obs = f"ERRO: {e}"
            state_log.append(f"[ciclo {cycle}] write_file({action.path}) -> {obs}")

        elif action.tool == "patch_file":
            try:
                patch_file(workdir, action.path, action.old or "", action.content or "")
                obs = "trecho substituido com sucesso."
            except ToolError as e:
                obs = f"ERRO: {e}"
            state_log.append(f"[ciclo {cycle}] patch_file({action.path}) -> {obs}")
            if verbose:
                print(f"  [ciclo {cycle}] patch_file -> {obs}", flush=True)

        elif action.tool == "run_tests":
            obs = run_tests(workdir)
            state_log.append(f"[ciclo {cycle}] run_tests() ->\n{obs}")

        elif action.tool == "done":
            state_log.append(f"[ciclo {cycle}] done() -- agente declarou que terminou.")
            break

    result = task.verify(workdir)
    return EpisodeResult(
        strategy=f"iterative_{edit_tool}",
        final_task_result=result,
        generations=generations,
        extracted_code=None,
        parse_ok=all_cycles_parsed,
    )
