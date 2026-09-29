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

`edit_tool` escolhe write_file ou patch_file dentro do protocolo
"structured" -- ver docs/NEGATIVE_RESULTS.md (H2).

`protocol` escolhe entre "structured" (tags <action>/TOOL:/PATH:) e
"simple" (comandos de uma linha + marcadores de conflito estilo git,
calibrado para modelos pequenos -- ver docs/NEGATIVE_RESULTS.md,
qwen3.5:0.8b). "simple" so suporta patch (nao write_file).

A logica de retry apos corte de orcamento e a mesma nos dois
protocolos: tenta parsear a resposta; se falhar E o corte foi por
orcamento, tenta UMA continuacao e parseia de novo -- nao depende de
checar uma substring de fechamento especifica de um protocolo.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import List, Optional

from pandaforge.backend.llama_server import LlamaServerBackend
from pandaforge.tasks.base import PyDebugTask
from pandaforge.tools.fs import read_file, write_file, patch_file, ToolError
from pandaforge.tools.pyexec import run_tests
from pandaforge.tools.protocol import (
    Action,
    parse_action,
    parse_action_simple,
    ActionParseError,
    TOOL_INSTRUCTIONS_WRITE,
    TOOL_INSTRUCTIONS_PATCH,
    SIMPLE_TOOL_INSTRUCTIONS,
    with_decoys,
)
from pandaforge.strategies.single_shot import EpisodeResult, _iter_source_files


def _build_cycle_prompt(objective: str, state_log: List[str], instructions: str) -> str:
    recent = "\n\n".join(state_log[-6:])
    body = (
        objective
        + "\n\n" + instructions
        + "\n\nHistorico recente (mais recente por ultimo):\n"
        + (recent or "(inicio -- nenhuma acao executada ainda)")
        + "\n\nPense brevemente sobre o proximo passo e emita UMA acao."
    )
    return f"<|im_start|>user\n{body}<|im_end|>\n<|im_start|>assistant\n"


def _get_action(
    backend: LlamaServerBackend, prompt: str, parser, close_tag: str,
    think_budget: int, continue_budget: int, cycle: int, verbose: bool,
    extra_valid_tools: set[str] | None = None,
) -> tuple[Optional[Action], Optional[str], list]:
    """
    Chama o modelo, tenta parsear a acao; se cortou pelo orcamento e o
    parsing falhou, tenta UMA continuacao e parseia de novo. Devolve
    (action_ou_None, mensagem_de_erro_ou_None, geracoes_desta_chamada).
    """
    generations = []
    gen = backend.complete(prompt, n_predict=think_budget, temperature=0.6)
    generations.append(gen)
    text = gen.content
    if verbose:
        print(f"  [ciclo {cycle}] chamada 1: {gen.wall_time_s:.1f}s, "
              f"{gen.tokens_predicted} tok, stop_type={gen.stop_type!r}", flush=True)

    try:
        return parser(text, extra_valid_tools=extra_valid_tools), None, generations
    except ActionParseError as e:
        if not gen.hit_budget_limit:
            return None, str(e), generations

    gen2 = backend.continue_after_budget(
        prompt, gen, n_predict=continue_budget, close_tag=close_tag
    )
    generations.append(gen2)
    text = text + gen2.content
    if verbose:
        print(f"  [ciclo {cycle}] chamada 2 (continuacao): {gen2.wall_time_s:.1f}s, "
              f"{gen2.tokens_predicted} tok, stop_type={gen2.stop_type!r}", flush=True)
    try:
        return parser(text, extra_valid_tools=extra_valid_tools), None, generations
    except ActionParseError as e2:
        return None, str(e2), generations


def run_iterative(
    backend: LlamaServerBackend,
    task: PyDebugTask,
    workdir: Path,
    think_budget: int = 500,
    continue_budget: int = 250,
    max_cycles: int = 6,
    edit_tool: str = "write",   # "write" ou "patch" -- so vale para protocol="structured"
    protocol: str = "structured",   # "structured" ou "simple"
    seed_files: List[str] | None = None,
    decoy_tools: List[str] | None = None,  # H4 (docs/HYPOTHESES.md)
    verbose: bool = True,
) -> EpisodeResult:
    if protocol not in ("structured", "simple"):
        raise ValueError(f"protocol invalido: {protocol!r} (use 'structured' ou 'simple')")
    if protocol == "simple":
        if edit_tool == "write":
            raise ValueError("protocol='simple' so suporta patch (edit_tool='write' nao existe nele)")
        instructions = with_decoys(SIMPLE_TOOL_INSTRUCTIONS, decoy_tools or [], style="simple")
        parser = parse_action_simple
        close_tag = ""  # nao forca fechamento -- deixa o modelo terminar o patch naturalmente
        strategy_name = "iterative_simple_patch"
    else:
        if edit_tool not in ("write", "patch"):
            raise ValueError(f"edit_tool invalido: {edit_tool!r} (use 'write' ou 'patch')")
        base_instructions = TOOL_INSTRUCTIONS_PATCH if edit_tool == "patch" else TOOL_INSTRUCTIONS_WRITE
        instructions = with_decoys(base_instructions, decoy_tools or [], style="structured")
        parser = parse_action
        close_tag = "\n</action>\n"
        strategy_name = f"iterative_{edit_tool}"

    if decoy_tools:
        strategy_name += f"_decoys{len(decoy_tools)}"
    extra_valid_tools = set(decoy_tools) if decoy_tools else None

    generations = []
    state_log: List[str] = []
    all_cycles_parsed = True
    n_decoy_calls = 0

    if seed_files is None:
        seed_files = [p.relative_to(workdir).as_posix() for p in _iter_source_files(workdir)]
    for seed_path in seed_files:
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
        prompt = _build_cycle_prompt(task.objective, state_log, instructions)
        action, err, cycle_gens = _get_action(
            backend, prompt, parser, close_tag,
            think_budget, continue_budget, cycle, verbose,
            extra_valid_tools=extra_valid_tools,
        )
        generations.extend(cycle_gens)

        if action is None:
            all_cycles_parsed = False
            state_log.append(
                f"[ciclo {cycle}] ERRO DE FORMATO: {err}. Siga o formato exatamente."
            )
            if verbose:
                print(f"  [ciclo {cycle}] ERRO DE FORMATO: {err} "
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
            if not obs.startswith("ERRO") and _auto_check_after_edit(
                task, workdir, cycle, state_log, verbose
            ):
                break

        elif action.tool == "patch_file":
            try:
                patch_file(workdir, action.path, action.old or "", action.content or "")
                obs = "trecho substituido com sucesso."
            except ToolError as e:
                obs = f"ERRO: {e}"
            state_log.append(f"[ciclo {cycle}] patch_file({action.path}) -> {obs}")
            if verbose:
                print(f"  [ciclo {cycle}] patch_file -> {obs}", flush=True)
            if not obs.startswith("ERRO") and _auto_check_after_edit(
                task, workdir, cycle, state_log, verbose
            ):
                break

        elif action.tool == "run_tests":
            obs = run_tests(workdir)
            state_log.append(f"[ciclo {cycle}] run_tests() ->\n{obs}")

        elif action.tool == "done":
            state_log.append(f"[ciclo {cycle}] done() -- agente declarou que terminou.")
            break

        else:
            # decoy tool (H4, docs/HYPOTHESES.md): existe no menu, o
            # parser aceitou, mas nao faz nada de verdade -- custa um
            # ciclo real, igual custaria no /pask escolher a tool errada.
            n_decoy_calls += 1
            obs = "ERRO: ferramenta nao disponivel para esta tarefa."
            state_log.append(f"[ciclo {cycle}] {action.tool}() -> {obs}")
            if verbose:
                print(f"  [ciclo {cycle}] DECOY escolhida: {action.tool} -> {obs}", flush=True)

    result = task.verify(workdir)
    return EpisodeResult(
        strategy=strategy_name,
        final_task_result=result,
        generations=generations,
        extracted_code=None,
        parse_ok=all_cycles_parsed,
        n_decoy_calls=n_decoy_calls,
    )


def _auto_check_after_edit(task: PyDebugTask, workdir: Path, cycle: int,
                            state_log: List[str], verbose: bool) -> bool:
    """
    Roda a verificacao real (pytest) logo apos uma edicao bem-sucedida,
    SEM depender do modelo lembrar de chamar run_tests -- descobrimos
    (ver docs/NEGATIVE_RESULTS.md) que ele pode nao verificar e so
    desperdicar ciclos repetindo a mesma edicao. Nao custa tokens (nao
    e uma chamada ao modelo). Devolve True se deve encerrar o loop.
    """
    result = task.verify(workdir)
    if result.passed:
        state_log.append(
            f"[auto, ciclo {cycle}] verificacao automatica pos-edicao: "
            f"TODOS OS TESTES PASSARAM -- encerrando."
        )
        if verbose:
            print(f"  [ciclo {cycle}] verificacao automatica: TODOS OS TESTES PASSARAM "
                  f"-- encerrando o loop.", flush=True)
        return True
    return False
