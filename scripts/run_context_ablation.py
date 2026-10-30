"""Small paired context ablation; uses existing strategies and ollama-bench RAM.

Run through panda py run-project. No installs, downloads or concurrent inference.
Only initial source availability differs: automatic seed vs read_file on demand.
"""
import argparse
import hashlib
import importlib.util
import json
import shutil
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pandaforge.backend.llama_server import LlamaServerBackend
from pandaforge.metrics import record_episode
from pandaforge.strategies import run_native_tools
from pandaforge.tasks import PyDebugTask

EXPERIMENT = "context-seed-ablation-2026-10-09"


def load_ram_probe(project_path):
    # Resolve with `panda projects path ollama-bench` before invoking this script.
    path = Path(project_path) / "bench.py"
    spec = importlib.util.spec_from_file_location("ollama_bench_resources", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.get_ram_used_mb, path


class ResourceProbe:
    """Sample system RAM and resident llama-server CPU/RSS, every 0.5s.

    CPU seconds are end-minus-start for the same PID; global RAM includes
    other apps. RSS is working set, not private/committed bytes or KV size.
    """
    def __init__(self, ram, psutil):
        self.ram = ram
        self.psutil = psutil
        self.stop = threading.Event()
        self.samples = []
        self.errors = []
        self.processes = [p for p in psutil.process_iter(["name"])
                          if (p.info["name"] or "").lower() == "llama-server.exe"]
        self.cpu_start = self.cpu_times()
        self.sample()
        self.thread = threading.Thread(target=self.loop, daemon=True)
        self.thread.start()

    def cpu_times(self):
        result = {}
        for p in self.processes:
            try:
                t = p.cpu_times()
                result[p.pid] = t.user + t.system
            except self.psutil.Error as e:
                self.errors.append(str(e))
        return result

    def sample(self):
        rss = []
        for p in self.processes:
            try:
                rss.append(p.memory_info().rss / 1024 ** 2)
            except self.psutil.Error as e:
                self.errors.append(str(e))
        self.samples.append({"system_ram_used_mb": self.ram(),
                             "server_rss_mb": sum(rss) if rss else None})

    def loop(self):
        while not self.stop.wait(0.5):
            self.sample()

    def finish(self):
        self.stop.set()
        self.thread.join()
        self.sample()
        cpu_end = self.cpu_times()
        system = [s["system_ram_used_mb"] for s in self.samples
                  if s["system_ram_used_mb"] is not None]
        rss = [s["server_rss_mb"] for s in self.samples if s["server_rss_mb"] is not None]
        return {"sample_interval_s": 0.5, "n_samples": len(self.samples),
                "server_pids": [p.pid for p in self.processes],
                "system_ram_start_mb": system[0] if system else None,
                "system_ram_peak_mb": max(system) if system else None,
                "server_rss_peak_mb": max(rss) if rss else None,
                "server_cpu_s": sum(cpu_end[pid] - start for pid, start in self.cpu_start.items()
                                    if pid in cpu_end) if cpu_end else None,
                "errors": sorted(set(self.errors))}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--validate-only", action="store_true")
    ap.add_argument("--bench-path", required=True,
                    help="Current ollama-bench path resolved by panda projects path")
    ap.add_argument("--output", default=f"results/{EXPERIMENT}.jsonl")
    ap.add_argument("--max-elapsed", type=float, default=420,
                    help="Soft battery cap; no new episode after this many seconds")
    args = ap.parse_args()
    import psutil  # installed dependency only; no installation fallback
    ram, ram_path = load_ram_probe(args.bench_path)
    tasks = [PyDebugTask.load(name) for name in ("py_debug_001", "py_debug_002")]
    fixture_hashes = {}
    for task in tasks:
        files = {p.relative_to(task.fixture_dir).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                 for p in sorted(task.fixture_dir.rglob("*")) if p.is_file() and "__pycache__" not in p.parts}
        fixture_hashes[task.name] = files
        workdir = task.setup()
        try:
            result = task.verify(workdir)
            expected = (2, 1) if task.name.endswith("001") else (3, 2)
            assert (result.n_passed, result.n_failed) == expected, result.stdout
            assert not result.passed
        finally:
            shutil.rmtree(workdir)
    print(f"Preflight OK: fixtures fail as expected; RAM={ram()} MB; psutil={psutil.__version__}", flush=True)
    if args.validate_only:
        return
    output = ROOT / args.output
    if output.exists():
        raise SystemExit(f"Refusing to mix/overwrite an existing experiment: {output}")
    backend = LlamaServerBackend(model="qwen3.5:0.8b", timeout_s=90)
    if not backend.is_online():
        raise SystemExit("llama-swap offline")
    started = time.monotonic()
    warmup_s = backend.warm_up()
    print(f"Warm-up excluded: {warmup_s:.2f}s", flush=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as out:
        for task in tasks:
            for seed in (20, 21):
                cells = ("seeded", "on_demand") if seed == 20 else ("on_demand", "seeded")
                for cell in cells:
                    if time.monotonic() - started >= args.max_elapsed:
                        print("Soft elapsed cap reached; battery incomplete", flush=True)
                        return
                    backend.seed = seed
                    workdir = task.setup()
                    probe = ResourceProbe(ram, psutil)
                    t0 = time.monotonic()
                    try:
                        ep = run_native_tools(backend, task, workdir, max_tokens=500,
                                              max_cycles=4, edit_tool="patch", decoy_tools=None,
                                              seed_files=None if cell == "seeded" else [],
                                              disable_thinking=True, verbose=False)
                        elapsed = time.monotonic() - t0
                        resources = probe.finish()
                        config = {"cell_label": cell, "seed": seed, "max_cycles": 4,
                                  "max_tokens": 500, "edit_tool": "patch", "decoy_tools": None,
                                  "disable_thinking": True,
                                  "seed_files": None if cell == "seeded" else [],
                                  "episode_elapsed_s": elapsed, "resources": resources}
                        record_episode(task.name, ep, backend.model, config, EXPERIMENT)
                        row = {"timestamp": datetime.now(timezone.utc).isoformat(),
                               "task": task.name, "cell": cell, "seed": seed,
                               "model": backend.model, "config": config,
                               "warmup_s": warmup_s, "fixture_sha256": fixture_hashes[task.name],
                               "ram_probe_path": str(ram_path),
                               "ram_probe_sha256": hashlib.sha256(ram_path.read_bytes()).hexdigest(),
                               "passed": ep.final_task_result.passed,
                               "n_passed": ep.final_task_result.n_passed,
                               "n_failed": ep.final_task_result.n_failed,
                               "pytest_stdout": ep.final_task_result.stdout,
                               "generated_tokens": ep.total_tokens, "n_calls": ep.n_calls,
                               "prompt_tokens_reported": sum(g.tokens_evaluated for g in ep.generations),
                               "raw_generations": [g.raw for g in ep.generations],
                               "final_source": {p.relative_to(workdir).as_posix(): p.read_text(encoding="utf-8")
                                                for p in sorted((workdir / "src").glob("*.py"))}}
                        out.write(json.dumps(row, ensure_ascii=False) + "\n")
                        out.flush()
                        print(f"{task.name} {cell} seed={seed}: passed={row['passed']} "
                              f"tokens={ep.total_tokens} calls={ep.n_calls} wall={elapsed:.1f}s "
                              f"cpu={resources['server_cpu_s']}s "
                              f"rss={resources['server_rss_peak_mb']}MB", flush=True)
                    finally:
                        if not probe.stop.is_set():
                            probe.finish()
                        shutil.rmtree(workdir)
    print(f"Completed in {time.monotonic() - started:.1f}s (including warm-up)", flush=True)


if __name__ == "__main__":
    main()
