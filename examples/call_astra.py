"""Make an authenticated Chat Completions request to Astra."""
import os
from urllib.parse import urlsplit

from openai import OpenAI


def main():
    host = os.environ.get("ASTRA_HOST", "").strip().lower()
    key = os.environ.get("ASTRA_API_KEY", "").strip()
    if not host or not key:
        raise ValueError("Set ASTRA_HOST and ASTRA_API_KEY before calling Astra.")
    base_url = f"https://{host}/v1"
    endpoint = urlsplit(base_url)
    if endpoint.netloc != host or endpoint.hostname != host or endpoint.path != "/v1" or any(c.isspace() for c in host):
        raise ValueError("ASTRA_HOST must be a DNS hostname without a scheme, path or port.")

    with OpenAI(
        base_url=base_url,
        api_key=key,
        timeout=120.0,
        max_retries=0,
    ) as client:
        response = client.chat.completions.create(
            model="astra",
            messages=[
                {"role": "user", "content": "Explain a Kubernetes Service in two sentences."}
            ],
            max_tokens=160,
            stream=False,
        )

    answer = response.choices[0].message.content if response.choices else None
    if not answer or not answer.strip():
        raise RuntimeError("Astra returned no answer text. Check the response limits and serving configuration.")
    print(answer)


if __name__ == "__main__":
    main()
