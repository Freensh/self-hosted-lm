"""Check the real Astra endpoint without printing application keys."""

import argparse
import json
import os
import re
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener


class NoRedirect(HTTPRedirectHandler):
    """Do not forward an application key to a redirected address."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def assess(status, body, expected):
    """A pass needs an answer, or an explicit authentication rejection."""
    try:
        data = json.loads(body)
    except (ValueError, UnicodeError):
        return False
    if not isinstance(data, dict):
        return False
    if expected == "denied":
        return status in (401, 403) and isinstance(data.get("error"), dict)
    if expected != "allowed" or status != 200:
        return False
    try:
        answer = data["choices"][0]["message"]["content"]
        return isinstance(answer, str) and bool(answer.strip())
    except (KeyError, IndexError, TypeError):
        return False


def request(host, key=None):
    """Use raw HTTP here so the test can deliberately omit authentication."""
    if not re.fullmatch(r"[A-Za-z0-9.-]+", host) or "." not in host:
        raise ValueError(
            "Set ASTRA_HOST to the approved DNS hostname, without a URL path"
        )
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = "Bearer " + key
    payload = {
        "model": "astra",
        "messages": [{"role": "user", "content": "Reply with a short greeting."}],
        "max_tokens": 64,
        "stream": False,
    }
    req = Request(
        "https://" + host + "/v1/chat/completions",
        data=json.dumps(payload).encode(),
        headers=headers,
    )
    try:
        with build_opener(NoRedirect()).open(req, timeout=120) as response:
            return response.status, response.read(1024 * 1024)
    except HTTPError as error:
        with error:
            return error.code, error.read(1024 * 1024)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--expect", choices=["allowed", "denied"], required=True)
    parser.add_argument(
        "--key-env",
        help="Environment variable containing the test key; omit to send no key",
    )
    args = parser.parse_args()
    try:
        key = os.environ[args.key_env] if args.key_env else None
        if args.key_env and not key.strip():
            raise ValueError("The key environment variable is empty")
        status, body = request(os.environ["ASTRA_HOST"], key)
        passed = assess(status, body, args.expect)
        print(
            json.dumps(
                {
                    "check": "endpoint_" + args.expect,
                    "http_status": status,
                    "result": "PASS" if passed else "FAIL",
                }
            )
        )
        return 0 if passed else 1
    except (KeyError, ValueError, URLError, OSError):
        print(
            json.dumps(
                {
                    "check": "endpoint_" + args.expect,
                    "result": "FAIL",
                    "reason": "Check hostname, key variable, private connectivity and TLS",
                }
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
