import json
import sys
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

payload = {
    "model": "qwen3.5:0.8b",
    "messages": [{"role": "user", "content": "Quanto e 17 * 23?"}],
    "max_tokens": 300,
    "temperature": 0.6,
}
req = urllib.request.Request(
    "http://localhost:8081/v1/chat/completions",
    data=json.dumps(payload).encode("utf-8"),
    headers={"Content-Type": "application/json"},
    method="POST",
)
with urllib.request.urlopen(req, timeout=120) as resp:
    body = json.loads(resp.read().decode("utf-8"))
print(json.dumps(body, indent=2, ensure_ascii=False)[:3000])
