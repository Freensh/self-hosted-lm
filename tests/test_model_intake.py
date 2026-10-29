import json
import unittest
from unittest.mock import patch
from model_intake import collect, make_manifest

REPO = "Qwen/test-candidate"
REV = "a" * 40


class IntakeTests(unittest.TestCase):
    def setUp(self):
        names = ["config.json", "tokenizer_config.json", "tokenizer.json",
                 "LICENSE", "README.md", "chat_template.jinja", "model.safetensors"]
        self.info = {"id": REPO, "sha": REV, "cardData": {"license": "apache-2.0"},
                     "siblings": [{"rfilename": n, "size": 100} for n in names]}
        self.config = {"model_type": "fixture"}

    def build(self):
        return make_manifest(REPO, REV, self.info, self.config, {}, {})

    def test_candidate_is_not_release_approval(self):
        result = self.build()
        self.assertEqual(result["status"], "candidate_unapproved")
        self.assertFalse(result["weight_hashes_verified"])
        self.assertEqual(result["reported_weight_bytes"], 100)

    def test_mutable_revision_is_rejected_before_network(self):
        with patch("model_intake.fetch") as network:
            with self.assertRaisesRegex(ValueError, "immutable"):
                collect(REPO, "main")
            network.assert_not_called()

    def test_wrong_source_identity(self):
        self.info["sha"] = "b" * 40
        with self.assertRaisesRegex(ValueError, "identity"):
            self.build()

    def test_missing_tokenizer(self):
        self.info["siblings"] = [x for x in self.info["siblings"]
                                 if x["rfilename"] != "tokenizer.json"]
        with self.assertRaisesRegex(ValueError, "Tokenizer"):
            self.build()

    def test_remote_code_mapping(self):
        self.config["auto_map"] = {"AutoModel": "custom.Model"}
        with self.assertRaisesRegex(ValueError, "Custom code"):
            self.build()

    def test_inventory_paths(self):
        for name in ("../weights", "/weights", "C:\\weights", "config.json"):
            with self.subTest(name=name):
                self.info["siblings"].append({"rfilename": name})
                with self.assertRaisesRegex(ValueError, "Unsafe or duplicate"):
                    self.build()
                self.info["siblings"].pop()

    def test_unknown_weight_size(self):
        self.info["siblings"][-1]["size"] = None
        with self.assertRaisesRegex(ValueError, "Weight size"):
            self.build()

    def test_missing_license(self):
        self.info["cardData"] = {}
        with self.assertRaisesRegex(ValueError, "License"):
            self.build()

    def test_collector_requests_only_pinned_metadata(self):
        payloads = [json.dumps(self.info).encode(), b'{}', b'{}', b'license', b'card']
        with patch("model_intake.fetch", side_effect=payloads) as network:
            result = collect(REPO, REV)
        paths = [call.args[0] for call in network.call_args_list]
        self.assertEqual(paths, [f"/api/models/{REPO}/revision/{REV}?blobs=true"]
                         + [f"/{REPO}/resolve/{REV}/{name}" for name in
                            ("config.json", "tokenizer_config.json", "LICENSE", "README.md")])
        self.assertEqual(len(result["downloaded_metadata_sha256"]), 5)
        self.assertFalse(result["weights_downloaded"])


if __name__ == "__main__":
    unittest.main()
