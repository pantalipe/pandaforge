"""
Ferramenta run_tests -- roda pytest dentro do workdir e devolve um
RESUMO curto (nao a saida bruta inteira), porque isso vira observacao
no proximo ciclo e precisa caber no orcamento de contexto.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def run_tests(workdir: Path, timeout_s: float = 30.0, max_chars: int = 1200) -> str:
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "-q"],
        cwd=workdir,
        capture_output=True,
        text=True,
        timeout=timeout_s,
    )
    output = proc.stdout.strip()
    if len(output) > max_chars:
        # mantem o FIM da saida -- e onde ficam o resumo e os tracebacks
        output = "...[inicio truncado]...\n" + output[-max_chars:]
    if proc.returncode == 0:
        return f"TODOS OS TESTES PASSARAM.\n{output}"
    return f"TESTES FALHARAM (codigo={proc.returncode}).\n{output}"
