"""Check the real pinned SDK with a local simulated HTTP transport."""
import contextlib
import io
import json
import os
import unittest
from unittest.mock import patch

import httpx2
from openai import AuthenticationError, OpenAI

from examples import call_astra


class ChatCompletionsExampleTests(unittest.TestCase):
    def run_example(self, handler):
        def client_factory(**kwargs):
            return OpenAI(
                http_client=httpx2.Client(transport=httpx2.MockTransport(handler)),
                **kwargs,
            )

        output = io.StringIO()
        with patch.dict(os.environ, {
            "ASTRA_HOST": "astra.example.com",
            "ASTRA_API_KEY": "synthetic-application-key",
            "OPENAI_BASE_URL": "https://unused.example.org/v1",
        }, clear=True), patch.object(call_astra, "OpenAI", side_effect=client_factory), contextlib.redirect_stdout(output):
            call_astra.main()
        return output.getvalue()

    def test_sdk_sends_authenticated_chat_completion_to_astra(self):
        def handler(request):
            self.assertEqual(str(request.url), "https://astra.example.com/v1/chat/completions")
            self.assertEqual(request.method, "POST")
            self.assertEqual(request.headers["authorization"], "Bearer synthetic-application-key")
            payload = json.loads(request.content)
            self.assertEqual(payload["model"], "astra")
            self.assertEqual(payload["messages"][0]["role"], "user")
            return httpx2.Response(200, json={
                "id": "synthetic-completion", "object": "chat.completion", "created": 0,
                "model": "astra", "choices": [{"index": 0, "finish_reason": "stop",
                    "message": {"role": "assistant", "content": "Synthetic test answer."}}],
            })

        self.assertEqual(self.run_example(handler), "Synthetic test answer.\n")

    def test_missing_or_invalid_host_stops_before_client_creation(self):
        for host in ("", "https://astra.example.com", "astra.example.com/v1?query=1"):
            with self.subTest(host=host), patch.dict(os.environ, {
                "ASTRA_HOST": host, "ASTRA_API_KEY": "synthetic-key",
            }, clear=True), patch.object(call_astra, "OpenAI") as constructor:
                with self.assertRaises(ValueError):
                    call_astra.main()
                constructor.assert_not_called()

    def test_rejected_key_is_reported_as_authentication_error(self):
        def handler(request):
            return httpx2.Response(401, json={"error": {
                "message": "Synthetic rejected key", "type": "authentication_error",
            }})

        with self.assertRaises(AuthenticationError):
            self.run_example(handler)


if __name__ == "__main__":
    unittest.main()
