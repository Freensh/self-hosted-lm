"""Load only pinned, hash-verified release files. No Hugging Face access."""

import argparse
import hashlib
import json
import os
import re
from pathlib import Path

MANIFEST_LIMIT = 4 * 1024 * 1024
CHUNK_SIZE = 1024 * 1024


def safe_path(name):
    """Keep each downloaded file inside the model directory."""
    if not isinstance(name, str) or "\\" in name or ":" in name:
        raise ValueError("Invalid artifact path")
    parts = name.split("/")
    for part in parts:
        if part in ("", ".", ".."):
            raise ValueError("Invalid artifact path")
    return Path(name)


def validate_manifest(manifest):
    """Require pinned images, object versions, file sizes and checksums."""
    if manifest.get("schema") != 1 or not manifest.get("release_id"):
        raise ValueError("Unknown release manifest")
    if not re.fullmatch(
        r"[^@]+@sha256:[a-f0-9]{64}", manifest.get("runtime_image", "")
    ):
        raise ValueError("Pin the runtime image digest")
    entries = manifest.get("files")
    if not isinstance(entries, list) or not entries:
        raise ValueError("Empty release")
    names = set()
    has_weights = False
    for entry in entries:
        name = entry["path"]
        safe_path(name)
        if name in names:
            raise ValueError("Duplicate path")
        names.add(name)
        if name.endswith(".safetensors"):
            has_weights = True
        if not re.fullmatch(r"[a-f0-9]{64}", entry["sha256"]):
            raise ValueError("Invalid checksum")
        if not entry.get("version_id") or entry["version_id"] == "null":
            raise ValueError("Object version required")
        if type(entry.get("bytes")) is not int or entry["bytes"] <= 0:
            raise ValueError("Invalid byte count")
    if "config.json" not in names or not has_weights:
        raise ValueError("Model configuration or weights missing")
    return entries


def copy_verified(body, destination, expected_hash, expected_bytes):
    """Download to a temporary file, then keep it only if its hash matches."""
    destination = Path(destination)
    temporary = destination.with_name(destination.name + ".partial")
    digest = hashlib.sha256()
    count = 0
    created = False
    try:
        with temporary.open("xb") as output:
            created = True
            while True:
                chunk = body.read(CHUNK_SIZE)
                if not chunk:
                    break
                count += len(chunk)
                if count > expected_bytes:
                    raise ValueError("Object exceeds manifest size")
                digest.update(chunk)
                output.write(chunk)
        if count != expected_bytes or digest.hexdigest() != expected_hash:
            raise ValueError("Artifact integrity mismatch")
        if destination.exists():
            raise FileExistsError(destination)
        os.replace(temporary, destination)
    finally:
        body.close()
        if created:
            temporary.unlink(missing_ok=True)


def load_release(s3, bucket, key, version, expected_hash, directory):
    # 1. Read the exact manifest version and check its checksum.
    response = s3.get_object(Bucket=bucket, Key=key, VersionId=version)
    with response["Body"] as body:
        raw = body.read(MANIFEST_LIMIT + 1)
    if len(raw) > MANIFEST_LIMIT or hashlib.sha256(raw).hexdigest() != expected_hash:
        raise ValueError("Release manifest hash mismatch")
    manifest = json.loads(raw)
    entries = validate_manifest(manifest)
    # 2. Download every listed object into an empty directory.
    root = Path(directory)
    root.mkdir(parents=True, exist_ok=True)
    existing_files = list(root.iterdir())
    if existing_files:
        raise ValueError("Use an empty model directory")
    for item in entries:
        destination = root / safe_path(item["path"])
        destination.parent.mkdir(parents=True, exist_ok=True)
        response = s3.get_object(
            Bucket=bucket, Key=item["key"], VersionId=item["version_id"]
        )
        copy_verified(response["Body"], destination, item["sha256"], item["bytes"])
    # 3. Record which verified release is ready to load.
    (root / "release-identity.json").write_text(
        json.dumps(
            {"release_id": manifest["release_id"], "manifest_sha256": expected_hash}
        ),
        encoding="utf-8",
    )
    return manifest["release_id"]


if __name__ == "__main__":
    import boto3

    parser = argparse.ArgumentParser()
    for name in ("bucket", "key", "version", "sha256", "directory"):
        parser.add_argument("--" + name, required=True)
    args = parser.parse_args()
    release = load_release(
        boto3.client("s3", region_name="us-east-1"),
        args.bucket,
        args.key,
        args.version,
        args.sha256,
        args.directory,
    )
    print(json.dumps({"release_id": release, "integrity": "verified"}))
