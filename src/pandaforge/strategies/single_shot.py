"""
Estrategias A (no_think) e B (think): UMA unica chamada ao modelo, com
a tarefa inteira no prompt (arquivo + saida da falha do teste).
Resposta esperada: o conteudo completo e corrigido de src/orders.py,
num bloco de codigo -- exatamente como o "estrategia A/B podem receber
a tarefa inteira e tentar resolver diretamente" da proposta original.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from pandaforge.backend.llama_server import LlamaServerBackend, Generation
from pandaforge.tasks.base import PyDebugTask, TaskResult
from pandaforge.tools.pyexec import run_tests
from pandaforge.strategies.prompts import TASK_OBJECTIVE

_CODE_BLOCK_RE = re.compile(r"```(?:python)?\s*\n(.*?)```", re.DOTALL)


@dataclass
class EpisodeResult:
    """Resultado de rodar uma estrategia inteira contra a tarefa."""
    strategy: str
    final_task_result: TaskResult
    generations: List[Generation]
    extracted_code: Optional[str] = None
    parse_ok: bool = True

    @property
    def total_tokens(self) -> int:
        return sum(g.tokens_predicted for g in self.generations)

    @property
    def total_wall_s(self) -> float:
        return sum(g.wall_time_s for g in self.generations)

    @property
    def n_calls(self) -> int:
        return len(self.generations)


def _extract_code(text: str) -> Optional[str]:
    matches = _CODE_BLOCK_RE.findall(text)
    if not matches:
        return None
    return matches[-1].strip() + "\n"


def _build_prompt(workdir: Path) -> str:
    source = (workdir / "src" / "orders.py").read_text(encoding="utf-8")
    failure = run_tests(workdir)
    return (
        TASK_OBJECTIVE
        + "\n\nConteudo atual de src/orders.py:\n```python\n" + source + "```"
        + "\n\nSaida da suite de testes:\n```\n" + failure + "\n```"
        + "\n\nResponda APENAS com o conteudo completo e corrigido de "
          "src/orders.py, dentro de um unico bloco ```python ... ```. "
          "Nao inclua nenhum outro texto fora do bloco."
    )


def _finish(strategy: str, task: PyDebugTask, workdir: Path,
            generations: List[Generation], raw_text: str) -> EpisodeResult:
    code = _extract_code(raw_text)
    if code is not None:
        task.write_source(workdir, "src/orders.py", code)
    result = task.verify(workdir)
    return EpisodeResult(
        strategy=strategy,
        final_task_result=result,
        generations=generations,
        extracted_code=code,
        parse_ok=code is not None,
    )


def run_no_think(
    backend: LlamaServerBackend, task: PyDebugTask, workdir: Path,
    max_tokens: int = 1024,
) -> EpisodeResult:
    prompt = _build_prompt(workdir)
    gen = backend.chat(
        messages=[{"role": "user", "content": "/no_think " + prompt}],
        max_tokens=max_tokens,
        temperature=0.2,
    )
    return _finish("no_think", task, workdir, [gen], gen.content)


def run_think(
    backend: LlamaServerBackend, task: PyDebugTask, workdir: Path,
    think_budget: int = 800,
) -> EpisodeResult:
    prompt_text = _build_prompt(workdir)
    prompt = f"<|im_start|>user\n{prompt_text}<|im_end|>\n<|im_start|>assistant\n"
    gen = backend.complete(prompt, n_predict=think_budget, temperature=0.6)
    return _finish("think", task, workdir, [gen], gen.content)
