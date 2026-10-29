"""Render explicit non-secret deployment variables; fail on missing values."""
import argparse
import os
import re
from pathlib import Path


def render(text, values):
    def substitute(match):
        key = match[1]
        value = values.get(key, "")
        if not value or "\n" in value or "\r" in value:
            raise ValueError(f"Missing or multiline value: {key}")
        if key.endswith("_IMAGE") and not re.fullmatch(r"[^\s]+@sha256:[a-f0-9]{64}", value):
            raise ValueError(f"Pin {key} by digest")
        return value
    return re.sub(r"\$\{([A-Z][A-Z0-9_]*)\}", substitute, text)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("input")
    parser.add_argument("output")
    args = parser.parse_args()
    result = render(Path(args.input).read_text(encoding="utf-8"), os.environ)
    with open(args.output, "x", encoding="utf-8") as destination:
        destination.write(result)
