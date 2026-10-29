import json
from pathlib import Path
import tempfile
import unittest
from release_requests import load_request, parse_changes
from start_release import request_arguments


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.request = dict(release_id="astra-001", pipeline_version=1,
                            manifest_uri="s3://test-evidence/candidates/001.json",
                            manifest_version="version-1", manifest_sha256="a"*64)

    def test_pins_pipeline_and_all_candidate_inputs(self):
        args = request_arguments("astra-001", self.request)
        self.assertEqual(args["PipelineVersionId"], 1)
        self.assertEqual(len(args["PipelineParameters"]), 4)
        self.assertEqual(args["ClientRequestToken"], request_arguments("astra-001", self.request)["ClientRequestToken"])

    def test_changed_request_has_new_idempotency_token(self):
        a = request_arguments("astra-001", self.request)["ClientRequestToken"]
        self.request["manifest_version"] = "version-2"
        self.assertNotEqual(a, request_arguments("astra-001", self.request)["ClientRequestToken"])

    def test_invalid_source_inputs_cannot_start(self):
        for key, value in [("pipeline_version", 0), ("pipeline_version", True),
                           ("manifest_sha256", "wrong"), ("manifest_uri", "https://example.org/file"),
                           ("manifest_version", "null"), ("manifest_version", 4),
                           ("manifest_version", "   "), ("manifest_sha256", None),
                           ("manifest_uri", []), ("release_id", "different")]:
            with self.subTest(key=key, value=value):
                candidate = dict(self.request, **{key: value})
                with self.assertRaises(ValueError):
                    request_arguments("astra-001", candidate)

    def test_unknown_and_traversal_release_ids_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            for release_id in ["missing", "../escape", "--option", "astra-"]:
                with self.subTest(release_id=release_id), self.assertRaises(ValueError):
                    load_request(release_id, Path(folder))

    def test_valid_file_and_unknown_fields(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/"astra-001.json"
            path.write_text(json.dumps(self.request), encoding="utf-8")
            self.assertEqual(load_request("astra-001", Path(folder)), self.request)
            self.request["unexpected"] = "value"
            path.write_text(json.dumps(self.request), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_request("astra-001", Path(folder))

    def test_only_new_release_files_are_selected(self):
        self.assertEqual(parse_changes("A\treleases/astra-001.json\nM\treleases/README.md\n"), ["astra-001"])

    def test_release_id_matches_sagemaker_display_name(self):
        for release_id in ["a", "astra-001", "a"*63]:
            self.assertEqual(request_arguments(release_id, dict(self.request, release_id=release_id))["PipelineExecutionDisplayName"], release_id)
        for release_id in ["astra-", "a"*64, "Astra"]:
            with self.subTest(release_id=release_id), self.assertRaises(ValueError):
                request_arguments(release_id, dict(self.request, release_id=release_id))

    def test_edits_deletions_and_nested_paths_are_rejected(self):
        for line in ["M\treleases/astra-001.json", "D\treleases/astra-001.json", "A\treleases/sub/astra-001.json"]:
            with self.subTest(line=line), self.assertRaises(ValueError):
                parse_changes(line)


if __name__ == "__main__":
    unittest.main()
