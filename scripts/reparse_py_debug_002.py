"""
Reaplica o parser corrigido em cima de geracoes JA CAPTURADAS no JSONL
(no_think e think da py_debug_002), sem gastar tempo de LLM de novo.
"""
import json
import sys
sys.path.insert(0, "C:/Users/panta/pandaforge/src")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from pandaforge.strategies.single_shot import _extract_files
from pandaforge.tasks import PyDebugTask

task = PyDebugTask.load("py_debug_002")

with open("C:/Users/panta/pandaforge/results/py_debug_002.jsonl", encoding="utf-8") as f:
    records = [json.loads(line) for line in f]

for rec in records:
    content = rec["generations"][0]["content"]
    files = _extract_files(content)
    print(f"\n=== {rec['strategy']} ===")
    print(f"arquivos extraidos: {list(files.keys())}")
    if not files:
        print("NADA extraido -- parser ainda falhou.")
        continue
    workdir = task.setup()
    for rel_path, new_content in files.items():
        task.write_source(workdir, rel_path, new_content)
    result = task.verify(workdir)
    print(f"resultado com parser corrigido: {result.summary}")
