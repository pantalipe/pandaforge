"""Deterministic regression check for native tool-call conversation history.

Run with ``panda py run-project pandaforge scripts/check_native_tool_history.py``.
No live server or model is used.
"""

from __future__ import annotations

import copy
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pandaforge.backend.llama_server import Generation
from pandaforge.strategies.native_tools import run_native_tools
from pandaforge.tasks.base import TaskResult


def tool_call(call_id: str, name: str, arguments: dict) -> dict:
    import json

    return {
        "id": call_id,
        "type": "function",
        "function": {"name": name, "arguments": json.dumps(arguments)},
    }


class FakeTask:
    objective = "Inspect the fixture and finish without changing it."

    def verify(self, workdir: Path) -> TaskResult:
        unchanged = (workdir / "src" / "sample.py").read_text(encoding="utf-8") == "value = 1\n"
        return TaskResult(
            passed=unchanged,
            returncode=0 if unchanged else 1,
            stdout="fixture unchanged" if unchanged else "fixture changed",
            stderr="",
            n_passed=1 if unchanged else 0,
            n_failed=0 if unchanged else 1,
        )


class FakeBackend:
    model = "fake-model"
    seed = 7

    def __init__(self, generations: list[Generation]):
        self.generations = generations
        self.snapshots: list[list[dict]] = []

    def chat(self, messages: list[dict], **_kwargs) -> Generation:
        self.snapshots.append(copy.deepcopy(messages))
        if not self.generations:
            raise AssertionError("strategy requested an unexpected extra model call")
        return self.generations.pop(0)


def make_generation(calls: list[dict]) -> Generation:
    return Generation(content="", tool_calls=calls)


def run_case(workdir: Path, first_calls: list[dict], expected_echo_calls: list[str]) -> None:
    original_proposals = copy.deepcopy(first_calls)
    first = make_generation(first_calls)
    final = make_generation([tool_call("done-after-read", "done", {})])
    backend = FakeBackend([first, final])

    episode = run_native_tools(
        backend,
        FakeTask(),
        workdir,
        max_tokens=32,
        max_cycles=3,
        seed_files=[],
        disable_thinking=True,
        verbose=False,
    )

    assert len(backend.snapshots) == 2, f"expected read then done; got {len(backend.snapshots)} calls"
    second_request = backend.snapshots[1]
    assistant_echoes = [m for m in second_request if m.get("role") == "assistant"]
    tool_replies = [m for m in second_request if m.get("role") == "tool"]
    assert len(assistant_echoes) == 1, f"expected one assistant tool-call echo: {second_request!r}"
    echoed_calls = assistant_echoes[0].get("tool_calls", [])
    echoed_ids = [call.get("id") for call in echoed_calls]
    assert echoed_ids == expected_echo_calls, (
        f"assistant echo must contain only executed calls {expected_echo_calls}; got {echoed_ids}"
    )
    assert len(tool_replies) == 1 and tool_replies[0].get("tool_call_id") == "read-source", (
        f"expected exactly one read-source result: {tool_replies!r}"
    )
    assert first.tool_calls == original_proposals, "preserve every proposed call on the raw Generation"
    assert episode.generations[0].tool_calls == original_proposals, (
        "episode result should retain every proposal on its original Generation"
    )
    assert episode.final_task_result.passed, "done should leave the fixture unchanged"
    assert backend.generations == [], "all simulated generations should be consumed"


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="pandaforge_tool_history_") as temp:
        workdir = Path(temp)
        source = workdir / "src" / "sample.py"
        source.parent.mkdir(parents=True)
        source.write_text("value = 1\n", encoding="utf-8")

        # Control: a one-tool response must remain a one-tool echo before done.
        run_case(
            workdir,
            [tool_call("read-source", "read_file", {"path": "src/sample.py"})],
            ["read-source"],
        )

        # Regression: the model proposes read + done together. Only read is
        # executed this cycle; done is proposed but must not be echoed as if
        # it had received a tool result. The following model turn may then done.
        run_case(
            workdir,
            [
                tool_call("read-source", "read_file", {"path": "src/sample.py"}),
                tool_call("done-unexecuted", "done", {}),
            ],
            ["read-source"],
        )

    print("PASS: single-tool history and read+done proposal history are consistent.")


if __name__ == "__main__":
    main()
