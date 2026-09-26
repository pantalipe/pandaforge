"""
Recorder de experimentos -- grava cada episodio (uma estrategia
rodando uma vez numa tarefa) como uma linha JSONL em
results/<task_name>.jsonl.

Uma linha = um episodio, com os campos BRUTOS (tokens/tempo/stop_type
por chamada), nao so o resumo -- para permitir reanalise depois sem
precisar rodar tudo de novo. E o "results/experiment_NNN.json ou
SQLite + exportacao" da proposta original, na versao mais simples que
funciona.
"""
from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pandaforge.metrics.env import capture_environment

RESULTS_DIR = Path(__file__).resolve().parents[3] / "results"


def _generation_to_dict(gen) -> dict[str, Any]:
    d = asdict(gen)
    d.pop("raw", None)  # resposta crua fica de fora do JSONL -- so os campos normalizados
    return d


def record_episode(
    task_name: str,
    episode,
    model: str,
    config: dict[str, Any],
    hypothesis: str = "",
    notes: str = "",
) -> Path:
    """
    Acrescenta uma linha em results/<task_name>.jsonl com o que
    precisamos pra reproduzir e comparar depois: ambiente, modelo,
    configuracao da estrategia, resultado objetivo (pytest, nunca a
    auto-declaracao do agente) e as geracoes brutas.
    """
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path = RESULTS_DIR / f"{task_name}.jsonl"

    r = episode.final_task_result
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "task": task_name,
        "strategy": episode.strategy,
        "model": model,
        "hypothesis": hypothesis,
        "config": config,
        "environment": capture_environment().as_dict(),
        "result": {
            "passed": r.passed,
            "returncode": r.returncode,
            "n_passed": r.n_passed,
            "n_failed": r.n_failed,
        },
        "total_tokens_predicted": episode.total_tokens,
        "total_wall_s": episode.total_wall_s,
        "n_calls": episode.n_calls,
        "parse_ok": episode.parse_ok,
        "generations": [_generation_to_dict(g) for g in episode.generations],
        "notes": notes,
    }
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return path
