"""Allow a release only when its identity, checks, approval and expiry pass."""

from datetime import datetime, timezone

REQUIRED = {
    "provenance",
    "license",
    "file_integrity",
    "file_format",
    "malware",
    "runtime_scan",
    "compatibility",
    "tool_calls",
    "safety",
    "performance",
}
SUBJECT_KEYS = {"manifest_sha256", "runtime_digest", "evalset_sha256", "policy_sha256"}


def release_decision(evidence, expected, now=None):
    """Return (allowed, reasons); never promote a file or approve a model."""
    now = now or datetime.now(timezone.utc)
    reasons = []
    if not isinstance(evidence, dict) or not isinstance(expected, dict):
        return False, ["Malformed evidence or expected release"]
    # 1. Make sure the evidence belongs to this release and these exact inputs.
    if (
        not expected.get("release_id")
        or evidence.get("release_id") != expected["release_id"]
    ):
        reasons.append("Release identity mismatch")
    subject = evidence.get("subject", {})
    if not isinstance(subject, dict):
        subject = {}
    for key in sorted(SUBJECT_KEYS):
        if not expected.get(key) or subject.get(key) != expected[key]:
            reasons.append(f"Subject mismatch: {key}")
    # 2. Require every scan/evaluation result and registry approval.
    checks = evidence.get("checks", {})
    if not isinstance(checks, dict):
        checks = {}
    for name in sorted(REQUIRED):
        if checks.get(name) != "PASS":
            reasons.append(f"Required check incomplete or failed: {name}")
    if evidence.get("registry_status") != "Approved":
        reasons.append("Registry approval missing")
    # 3. Reject expired evidence, even when earlier checks passed.
    try:
        expires = datetime.fromisoformat(evidence["valid_until"].replace("Z", "+00:00"))
        if expires.tzinfo is None or expires <= now:
            reasons.append("Evidence expired or missing timezone")
    except (KeyError, TypeError, ValueError, AttributeError):
        reasons.append("Invalid evidence expiry")
    return not reasons, reasons
