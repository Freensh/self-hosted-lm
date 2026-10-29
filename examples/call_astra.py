import json
import os
from urllib.request import Request, urlopen

host = os.environ["ASTRA_HOST"]
key = os.environ["ASTRA_API_KEY"]
payload = {
    "model": "astra",
    "messages": [{"role": "user", "content": "Explain a Kubernetes Service in two sentences."}],
    "max_tokens": 160,
    "stream": False,
}
request = Request(
    f"https://{host}/v1/chat/completions",
    data=json.dumps(payload).encode(),
    headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
)
with urlopen(request, timeout=120) as response:
    result = json.load(response)
print(result["choices"][0]["message"]["content"])
