"""Teste rapido, sem LLM, do protocolo patch_file + parse_action."""
import sys
sys.path.insert(0, "C:/Users/panta/pandaforge/src")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from pandaforge.tools.protocol import parse_action
from pandaforge.tools.fs import patch_file
from pandaforge.tasks import PyDebugTask

fake_response = '''Vou corrigir o desconto.

<action>
TOOL: patch_file
PATH: src/orders.py
OLD:
    return round(total - (total * discount_fraction / 100), 2)
NEW:
    return round(total - (total * discount_fraction), 2)
</action>'''

action = parse_action(fake_response)
print("tool:", action.tool)
print("path:", action.path)
print("old :", repr(action.old))
print("new :", repr(action.content))

task = PyDebugTask.load("py_debug_001")
workdir = task.setup()
patch_file(workdir, action.path, action.old, action.content)
result = task.verify(workdir)
print("\nresultado apos patch:", result.summary)
assert result.passed, "patch_file nao corrigiu o bug -- revisar antes de gastar tempo de LLM"
print("OK -- patch_file funciona como esperado.")
