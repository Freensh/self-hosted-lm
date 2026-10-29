import copy
import unittest
from datetime import datetime, timezone
from release_gate import REQUIRED, release_decision

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


class ReleaseGateTests(unittest.TestCase):
    def setUp(self):
        self.expected = {
            "release_id": "astra-test-001",
            "manifest_sha256": "a" * 64,
            "runtime_digest": "sha256:" + "b" * 64,
            "evalset_sha256": "c" * 64,
            "policy_sha256": "d" * 64,
        }
        self.evidence = {
            "release_id": self.expected["release_id"],
            "subject": {k: v for k, v in self.expected.items() if k != "release_id"},
            "checks": {name: "PASS" for name in REQUIRED},
            "registry_status": "Approved",
            "valid_until": "2026-01-02T00:00:00Z",
        }

    def decide(self, evidence=None):
        return release_decision(self.evidence if evidence is None else evidence, self.expected, NOW)[0]

    def test_complete_matching_evidence_passes(self):
        self.assertTrue(self.decide())

    def test_every_missing_check_blocks(self):
        for name in REQUIRED:
            with self.subTest(name=name):
                evidence = copy.deepcopy(self.evidence)
                del evidence["checks"][name]
                self.assertFalse(self.decide(evidence))

    def test_nonpassing_statuses_block(self):
        for status in ["FAIL", "SKIPPED", "ERROR", "UNKNOWN", "PENDING", True, None]:
            with self.subTest(status=status):
                self.evidence["checks"]["malware"] = status
                self.assertFalse(self.decide())

    def test_subject_changes_block(self):
        for name in self.evidence["subject"]:
            with self.subTest(name=name):
                evidence = copy.deepcopy(self.evidence)
                evidence["subject"][name] = "changed"
                self.assertFalse(self.decide(evidence))

    def test_wrong_release_blocks(self):
        self.evidence["release_id"] = "different-release"
        self.assertFalse(self.decide())

    def test_missing_approval_blocks(self):
        for status in ["PendingManualApproval", "Rejected", None]:
            self.evidence["registry_status"] = status
            self.assertFalse(self.decide())

    def test_expired_evidence_blocks(self):
        self.evidence["valid_until"] = "2025-12-31T23:59:59Z"
        self.assertFalse(self.decide())

    def test_expiry_at_boundary_blocks(self):
        self.evidence["valid_until"] = NOW.isoformat()
        self.assertFalse(self.decide())

    def test_malformed_expiry_blocks(self):
        for value in [None, "not-a-date", "2026-01-02T00:00:00"]:
            self.evidence["valid_until"] = value
            self.assertFalse(self.decide())

    def test_malformed_sections_block(self):
        for section in ["checks", "subject"]:
            evidence = copy.deepcopy(self.evidence)
            evidence[section] = None
            self.assertFalse(self.decide(evidence))

    def test_unset_expected_binding_blocks(self):
        del self.expected["policy_sha256"]
        self.assertFalse(self.decide())

    def test_non_object_evidence_blocks(self):
        self.assertFalse(release_decision(None, self.expected, NOW)[0])


if __name__ == "__main__":
    unittest.main()
