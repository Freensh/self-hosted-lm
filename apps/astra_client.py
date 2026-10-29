"""Create the shared OpenAI client used by the assistants."""

from urllib.parse import urlparse
import os
from openai import OpenAI


def make_client():
    endpoint = os.environ["OPENAI_BASE_URL"]
    expected_host = os.environ["ASTRA_HOST"]
    parsed = urlparse(endpoint)
    correct_host = parsed.hostname == expected_host
    correct_path = parsed.path.rstrip("/") == "/v1"
    if parsed.scheme != "https" or not correct_host or not correct_path:
        raise ValueError("Use the approved Astra HTTPS endpoint")
    return OpenAI(
        base_url=endpoint,
        api_key=os.environ["OPENAI_API_KEY"],
        timeout=60,
        max_retries=0,
    )
