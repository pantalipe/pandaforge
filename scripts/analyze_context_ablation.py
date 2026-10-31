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
    if not rows:
        raise SystemExit("No completed episodes to analyze")
    experiment = rows[0]["config"].get("experiment", EXPERIMENT)
    planned_tasks = rows[0]["config"].get("planned_tasks", ["py_debug_001", "py_debug_002"])
    planned_seeds = rows[0]["config"].get("planned_seeds", [20, 21])
    expected = len(planned_tasks) * len(planned_seeds) * 2
    hashes = {r["config"].get("native_strategy_sha256") for r in rows}
    assert len(hashes) == 1, "strategy changed during battery"
    assert all(r["config"].get("experiment", EXPERIMENT) == experiment for r in rows)
    assert all(r["config"].get("planned_tasks", planned_tasks) == planned_tasks for r in rows)
    historical = {name: [json.loads(line) for line in (ROOT / "results" / f"{name}.jsonl")
                        .read_text(encoding="utf-8").splitlines()]
                  for name in {r["task"] for r in rows}}
    groups = defaultdict(list)
    audited = []
    for row in rows:
        config = row["config"]
        matching = [r for r in historical[row["task"]] if r["hypothesis"] == experiment
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
        if "request_tool_history" in row:
            assert len(row["request_tool_history"]) == row["n_calls"]
            assert all(h["announced"] == h["answered"] for h in row["request_tool_history"])
        proposed = [g["choices"][0]["message"].get("tool_calls") or []
                    for g in row["raw_generations"]]
        first_calls = [calls[0]["function"] if calls else None for calls in proposed]
        trace = [{"name": fn["name"], "arguments": json.loads(fn["arguments"])}
                 if fn else {"name": "no_tool_call"} for fn in first_calls]
        audit = {"task": row["task"], "cell": row["cell"], "seed": row["seed"],
                 "passed": row["passed"], "executed_first_call_trace": trace,
                 "proposed_calls_per_generation": [len(calls) for calls in proposed],
                 "multi_call_generations": sum(len(calls) > 1 for calls in proposed)}
        if "request_tool_history" in row:
            audit["request_history_consistent"] = True
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
    summary = {"experiment": experiment, "expected_episodes": expected,
               "observed_episodes": len(rows), "incomplete": len(rows) != expected,
               "missing": [f"{task}:{cell}:seed{seed}" for task in planned_tasks
                           for cell in ("seeded", "on_demand") for seed in planned_seeds
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
