from urllib.parse import urlparse
import os
from openai import OpenAI

def make_client():
    endpoint = os.environ["OPENAI_BASE_URL"]
    expected_host = os.environ["ASTRA_HOST"]
    parsed = urlparse(endpoint)
    if parsed.scheme != "https" or parsed.hostname != expected_host or parsed.path.rstrip("/") != "/v1":
        raise ValueError("Use the approved approved Astra HTTPS endpoint")
    return OpenAI(base_url=endpoint, api_key=os.environ["OPENAI_API_KEY"],
                  timeout=60, max_retries=0)
