"""
Estrategias A (no_think) e B (think): UMA unica chamada ao modelo, com
a tarefa inteira no prompt (todos os arquivos .py em src/ + saida da
falha do teste). Resposta esperada: um ou mais blocos de codigo, cada
um comecando com um comentario '# file: <caminho>' seguido do conteudo
completo e corrigido daquele arquivo -- exatamente como o "estrategia
A/B podem receber a tarefa inteira e tentar resolver diretamente" da
proposta original. Generico o bastante pra tarefas com 1 ou varios
arquivos-fonte.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from pandaforge.backend.llama_server import LlamaServerBackend, Generation
from pandaforge.tasks.base import PyDebugTask, TaskResult
from pandaforge.tools.pyexec import run_tests

_CODE_BLOCK_RE = re.compile(
    r"#\s*file:\s*(\S+)\s*\n(.*?)(?=\n#\s*file:|```|\Z)",
    re.DOTALL | re.IGNORECASE,
)


@dataclass
class EpisodeResult:
    """Resultado de rodar uma estrategia inteira contra a tarefa."""
    strategy: str
    final_task_result: TaskResult
    generations: List[Generation]
    extracted_code: Optional[Dict[str, str]] = None
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


def _iter_source_files(workdir: Path) -> List[Path]:
    src_dir = workdir / "src"
    if not src_dir.is_dir():
        return []
    return sorted(src_dir.rglob("*.py"))


def _extract_files(text: str) -> Dict[str, str]:
    """Devolve {caminho_relativo: conteudo} para cada bloco '# file: X'."""
    out = {}
    for path, content in _CODE_BLOCK_RE.findall(text):
        out[path.strip()] = content.strip() + "\n"
    return out


def _build_prompt(task: PyDebugTask, workdir: Path) -> str:
    files = _iter_source_files(workdir)
    parts = [task.objective, "\nConteudo atual dos arquivos-fonte:"]
    for f in files:
        rel = f.relative_to(workdir).as_posix()
        parts.append(f"\n```python\n# file: {rel}\n{f.read_text(encoding='utf-8')}```")
    failure = run_tests(workdir)
    parts.append(f"\nSaida da suite de testes:\n```\n{failure}\n```")
    parts.append(
        "\nResponda com um ou mais blocos, cada um EXATAMENTE neste formato "
        "(com as crases):\n"
        "```python\n# file: caminho/exato/mostrado/acima.py\n"
        "<conteudo COMPLETO e corrigido deste arquivo>\n```\n"
        "So inclua arquivos que precisam mudar. Nao inclua nenhum outro "
        "texto fora dos blocos -- nem explicacao, nem comentario solto."
    )
    return "\n".join(parts)


def _finish(strategy: str, task: PyDebugTask, workdir: Path,
            generations: List[Generation], raw_text: str) -> EpisodeResult:
    files = _extract_files(raw_text)
    for rel_path, content in files.items():
        task.write_source(workdir, rel_path, content)
    result = task.verify(workdir)
    return EpisodeResult(
        strategy=strategy,
        final_task_result=result,
        generations=generations,
        extracted_code=files,
        parse_ok=bool(files),
    )


def run_no_think(
    backend: LlamaServerBackend, task: PyDebugTask, workdir: Path,
    max_tokens: int = 1024,
) -> EpisodeResult:
    prompt = _build_prompt(task, workdir)
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
    prompt_text = _build_prompt(task, workdir)
    prompt = f"<|im_start|>user\n{prompt_text}<|im_end|>\n<|im_start|>assistant\n"
    gen = backend.complete(prompt, n_predict=think_budget, temperature=0.6)
    return _finish("think", task, workdir, [gen], gen.content)
