"""Audit the context pilot against historical recorder rows; no inference."""
import argparse
import json
from collections import defaultdict
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parents[1]
EXPERIMENT = "context-seed-ablation-2026-10-09"


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", default=f"results/{EXPERIMENT}.jsonl")
    args = ap.parse_args()
    path = ROOT / args.input
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    historical = {name: [json.loads(line) for line in (ROOT / "results" / f"{name}.jsonl")
                        .read_text(encoding="utf-8").splitlines()]
                  for name in {r["task"] for r in rows}}
    groups = defaultdict(list)
    audited = []
    for row in rows:
        config = row["config"]
        matching = [r for r in historical[row["task"]] if r["hypothesis"] == EXPERIMENT
                    and r["config"]["seed"] == row["seed"]
                    and r["config"]["cell_label"] == row["cell"]
                    and r["config"].get("episode_elapsed_s") == config["episode_elapsed_s"]]
        assert len(matching) == 1, "missing/duplicate historical recorder entry"
        recorded = matching[0]
        assert recorded["result"]["passed"] == row["passed"]
        assert recorded["total_tokens_predicted"] == row["generated_tokens"]
        assert row["n_calls"] == len(row["raw_generations"])
        assert row["passed"] == (row["n_failed"] == 0 and row["n_passed"] in (3, 5))
        assert config["resources"]["server_pids"] and not config["resources"]["errors"]
        proposed = [g["choices"][0]["message"].get("tool_calls", [])
                    for g in row["raw_generations"]]
        first_calls = [calls[0]["function"] if calls else None for calls in proposed]
        trace = [{"name": fn["name"], "arguments": json.loads(fn["arguments"])}
                 if fn else {"name": "no_tool_call"} for fn in first_calls]
        audit = {"task": row["task"], "cell": row["cell"], "seed": row["seed"],
                 "passed": row["passed"], "executed_first_call_trace": trace,
                 "proposed_calls_per_generation": [len(calls) for calls in proposed],
                 "multi_call_generations": sum(len(calls) > 1 for calls in proposed)}
        audited.append(audit)
        groups[(row["task"], row["cell"])].append(row)
    cells = []
    for (task, cell), sample in groups.items():
        cells.append({"task": task, "cell": cell, "n": len(sample),
                      "passed": sum(r["passed"] for r in sample),
                      "seeds": [r["seed"] for r in sample],
                      "mean_generated_tokens": mean(r["generated_tokens"] for r in sample),
                      "mean_prompt_tokens_reported": mean(r["prompt_tokens_reported"] for r in sample),
                      "mean_episode_wall_s": mean(r["config"]["episode_elapsed_s"] for r in sample),
                      "mean_server_cpu_s": mean(r["config"]["resources"]["server_cpu_s"] for r in sample),
                      "mean_server_rss_peak_mb": mean(r["config"]["resources"]["server_rss_peak_mb"] for r in sample),
                      "mean_system_ram_peak_delta_mb": mean(
                          r["config"]["resources"]["system_ram_peak_mb"] -
                          r["config"]["resources"]["system_ram_start_mb"] for r in sample)})
    summary = {"experiment": EXPERIMENT, "expected_episodes": 8,
               "observed_episodes": len(rows), "incomplete": len(rows) != 8,
               "missing": [f"{task}:{cell}:seed{seed}" for task in ("py_debug_001", "py_debug_002")
                           for cell in ("seeded", "on_demand") for seed in (20, 21)
                           if not any(r["task"] == task and r["cell"] == cell and r["seed"] == seed
                                      for r in rows)],
               "warmup_s": rows[0]["warmup_s"],
               "total_episode_wall_s": sum(r["config"]["episode_elapsed_s"] for r in rows),
               "cells": cells, "audits": audited}
    target = path.with_suffix(".summary.json")
    target.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
