import json
import sys
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

payload = {
    "model": "qwen3.5:0.8b",
    "messages": [{"role": "user", "content": "Quanto e 17 * 23?"}],
    "max_tokens": 200,
    "temperature": 0.2,
    "chat_template_kwargs": {"enable_thinking": False},
}
req = urllib.request.Request(
    "http://localhost:8081/v1/chat/completions",
    data=json.dumps(payload).encode("utf-8"),
    headers={"Content-Type": "application/json"},
    method="POST",
)
with urllib.request.urlopen(req, timeout=120) as resp:
    body = json.loads(resp.read().decode("utf-8"))
msg = body["choices"][0]["message"]
print("content:", repr(msg.get("content")))
print("reasoning_content:", repr(msg.get("reasoning_content")))
print("finish_reason:", body["choices"][0]["finish_reason"])
print("completion_tokens:", body["usage"]["completion_tokens"])
