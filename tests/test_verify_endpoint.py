import json
import unittest
from verify_endpoint import assess, request


class EndpointTests(unittest.TestCase):
    def test_success_requires_a_real_answer(self):
        self.assertTrue(
            assess(
                200,
                json.dumps({"choices": [{"message": {"content": "Hello"}}]}),
                "allowed",
            )
        )
        for body in [
            "{}",
            "[]",
            "not-json",
            '{"choices": []}',
            '{"choices": [{"message": {"content": ""}}]}',
        ]:
            self.assertFalse(assess(200, body, "allowed"))

    def test_denial_requires_expected_status_and_error(self):
        body = '{"error": {"message": "Rejected"}}'
        for status in [401, 403]:
            self.assertTrue(assess(status, body, "denied"))
        for status in [200, 301, 429, 500, 503]:
            self.assertFalse(assess(status, body, "denied"))
        self.assertFalse(assess(403, "<html>Proxy error</html>", "denied"))

    def test_invalid_hosts_fail_before_network(self):
        for host in [
            "https://example.com",
            "example.com/path",
            "example.com@evil.test",
            "",
        ]:
            with self.subTest(host=host), self.assertRaises(ValueError):
                request(host)


if __name__ == "__main__":
    unittest.main()
