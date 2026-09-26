"""
Ferramentas de sistema de arquivos para a estrategia iterativa --
escopadas a um workdir (a copia isolada da fixture), sem escapar dele.
"""
from __future__ import annotations

from pathlib import Path


class ToolError(Exception):
    """Erro de uso de ferramenta -- vira observacao pro proximo ciclo,
    nao uma excecao que derruba o experimento."""


def _safe_path(workdir: Path, rel_path: str) -> Path:
    rel_path = rel_path.strip().lstrip("/\\")
    if not rel_path:
        raise ToolError("path vazio")
    candidate = (workdir / rel_path).resolve()
    workdir_resolved = workdir.resolve()
    if workdir_resolved != candidate and workdir_resolved not in candidate.parents:
        raise ToolError(f"path fora do workdir: {rel_path!r}")
    return candidate


def read_file(workdir: Path, rel_path: str, max_chars: int = 4000) -> str:
    path = _safe_path(workdir, rel_path)
    if not path.is_file():
        raise ToolError(f"arquivo nao encontrado: {rel_path!r}")
    content = path.read_text(encoding="utf-8", errors="replace")
    if len(content) > max_chars:
        content = content[:max_chars] + f"\n...[truncado, {len(content)} chars no total]"
    return content


def write_file(workdir: Path, rel_path: str, content: str) -> None:
    path = _safe_path(workdir, rel_path)
    if not path.parent.exists():
        raise ToolError(f"diretorio pai nao existe: {rel_path!r}")
    path.write_text(content, encoding="utf-8")


def patch_file(workdir: Path, rel_path: str, old: str, new: str) -> None:
    """
    Edicao cirurgica: substitui `old` por `new` no arquivo, exigindo
    que `old` apareca EXATAMENTE uma vez (mesmo criterio do
    memory_str_replace/str_replace) -- nunca reescreve o arquivo
    inteiro. E o mecanismo que testa H2 (docs/HYPOTHESES.md): reduz
    o tamanho da edicao por ciclo e, por construcao, so pode tocar
    no trecho que o modelo realmente leu/citou.
    """
    path = _safe_path(workdir, rel_path)
    if not path.is_file():
        raise ToolError(f"arquivo nao encontrado: {rel_path!r}")
    content = path.read_text(encoding="utf-8")
    count = content.count(old)
    if count == 0:
        raise ToolError(
            "OLD nao encontrado no arquivo -- confira se copiou o trecho "
            "EXATAMENTE como esta no arquivo (indentacao e quebras de linha incluidas)"
        )
    if count > 1:
        raise ToolError(
            f"OLD aparece {count} vezes no arquivo -- inclua mais linhas de "
            f"contexto em OLD para torna-lo unico"
        )
    path.write_text(content.replace(old, new, 1), encoding="utf-8")
