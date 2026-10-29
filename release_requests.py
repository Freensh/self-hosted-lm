"""Validate release requests and select only new files for a merged change."""

import argparse
import json
import re
import subprocess
from pathlib import Path
from start_release import RELEASE_ID_PATTERN, validate_request

ID = re.compile(RELEASE_ID_PATTERN)


def load_request(release_id, directory=Path("releases")):
    if not ID.fullmatch(release_id):
        raise ValueError("Invalid release ID")
    path = directory / (release_id + ".json")
    if path.is_symlink() or not path.is_file():
        raise ValueError("Release request must be an existing regular JSON file")
    request = json.loads(path.read_text(encoding="utf-8"))
    validate_request(release_id, request)
    return request


def parse_changes(output):
    """Select newly added release requests; existing requests cannot change."""
    ids = []
    for line in output.splitlines():
        status, path = line.split("\t", 1)
        if not path.startswith("releases/") or not path.endswith(".json"):
            continue
        name = path[len("releases/") : -5]
        if status != "A":
            raise ValueError("Release requests are immutable; add a new release ID")
        if not ID.fullmatch(name):
            raise ValueError("Invalid release request filename")
        ids.append(name)
    if len(ids) > 10:
        raise ValueError("Submit at most ten model release requests in one change")
    return sorted(set(ids))


def changed(base, head):
    """Check release requests introduced between two Git commits."""
    for revision in (base, head):
        if not re.fullmatch(r"[0-9a-f]{40}", revision) or revision == "0" * 40:
            raise ValueError("Provide existing full Git revisions")
    result = subprocess.run(
        ["git", "diff", "--no-renames", "--name-status", base, head, "--", "releases/"],
        check=True,
        capture_output=True,
        text=True,
    )
    ids = parse_changes(result.stdout)
    for release_id in ids:
        load_request(release_id)
    return ids


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["validate", "changed", "one"])
    parser.add_argument("values", nargs="*")
    args = parser.parse_args()
    try:
        if args.mode == "validate" and not args.values:
            for file in sorted(Path("releases").glob("*.json")):
                load_request(file.stem)
            print("Release requests are valid")
        elif args.mode == "changed" and len(args.values) == 2:
            print(json.dumps(changed(*args.values)))
        elif args.mode == "one" and len(args.values) == 1:
            load_request(args.values[0])
            print(json.dumps(args.values))
        else:
            parser.error("Incorrect arguments")
    except (ValueError, TypeError, OSError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"Release request check failed: {error}\n")
