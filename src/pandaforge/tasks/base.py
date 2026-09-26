"""
Task base do PandaForge: uma tarefa de debugging Python verificavel
de forma 100% deterministica via pytest -- sem LLM nenhum como juiz.

Fluxo:
    task = PyDebugTask.load("py_debug_001")
    workdir = task.setup()          # copia isolada da fixture (nunca
                                     # mexe no original)
    ... aqui entra o agente/estrategia, editando arquivos em workdir ...
    result = task.verify(workdir)   # roda pytest, devolve passed/failed

Cada chamada a setup() cria um diretorio temporario novo, entao
chamadas repetidas (varias estrategias, varios seeds) nunca vazam
estado entre si.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

SUITE_DIR = Path(__file__).parent / "suite"

_SUMMARY_RE = re.compile(
    r"(\d+) failed" r"|" r"(\d+) passed"
)


@dataclass
class TaskResult:
    passed: bool           # True sse todos os testes passaram (returncode 0)
    returncode: int
    stdout: str
    stderr: str
    n_passed: int
    n_failed: int

    @property
    def summary(self) -> str:
        return f"{self.n_passed} passed, {self.n_failed} failed (rc={self.returncode})"


_DEFAULT_OBJECTIVE = (
    "Ha um bug real em algum lugar do projeto e a suite de testes tem "
    "pelo menos 1 teste falhando. Descubra por que, corrija SOMENTE o "
    "bug real (nao reescreva o que ja funciona), e garanta que todos "
    "os testes passem."
)


class PyDebugTask:
    """
    Uma tarefa de debugging Python com fixture (projeto quebrado) +
    verificador (pytest). O criterio de sucesso e objetivo: os testes
    passam ou nao passam -- nenhum LLM avalia isso.

    Cada tarefa pode ter seu proprio objective.txt (em
    suite/<name>/objective.txt) com o enunciado especifico -- se nao
    existir, usa um enunciado generico.
    """

    def __init__(self, name: str, fixture_dir: Path, timeout_s: float = 30.0,
                 objective: str | None = None):
        self.name = name
        self.fixture_dir = fixture_dir
        self.timeout_s = timeout_s
        self.objective = objective or _DEFAULT_OBJECTIVE
        if not self.fixture_dir.is_dir():
            raise FileNotFoundError(f"fixture nao encontrada: {self.fixture_dir}")

    @classmethod
    def load(cls, name: str) -> "PyDebugTask":
        task_dir = SUITE_DIR / name
        fixture_dir = task_dir / "fixture"
        objective_path = task_dir / "objective.txt"
        objective = objective_path.read_text(encoding="utf-8") if objective_path.is_file() else None
        return cls(name=name, fixture_dir=fixture_dir, objective=objective)

    def setup(self) -> Path:
        """
        Copia fixture_dir para um diretorio temporario isolado e
        devolve o path da copia. O original em suite/<name>/fixture/
        nunca e tocado -- cada chamada comeca do mesmo estado quebrado.
        """
        workdir = Path(tempfile.mkdtemp(prefix=f"pandaforge_{self.name}_"))
        shutil.copytree(self.fixture_dir, workdir, dirs_exist_ok=True)
        return workdir

    def verify(self, workdir: Path) -> TaskResult:
        """
        Roda `python -m pytest tests/` dentro de workdir e devolve o
        resultado bruto. Determinístico: mesmo codigo em workdir sempre
        da o mesmo resultado (sem chamada a LLM aqui).
        """
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/", "-q"],
            cwd=workdir,
            capture_output=True,
            text=True,
            timeout=self.timeout_s,
        )
        n_passed = n_failed = 0
        for m in _SUMMARY_RE.finditer(proc.stdout):
            if m.group(1):
                n_failed = int(m.group(1))
            elif m.group(2):
                n_passed = int(m.group(2))
        return TaskResult(
            passed=(proc.returncode == 0),
            returncode=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            n_passed=n_passed,
            n_failed=n_failed,
        )

    def read_source(self, workdir: Path, rel_path: str) -> str:
        """Helper de leitura -- futura 'ferramenta' read_file do agente."""
        return (workdir / rel_path).read_text(encoding="utf-8")

    def write_source(self, workdir: Path, rel_path: str, content: str) -> None:
        """Helper de escrita -- futura 'ferramenta' write_file do agente."""
        (workdir / rel_path).write_text(content, encoding="utf-8")
