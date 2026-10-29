"""Download the recorded model revision and its permitted files."""

import json
from pathlib import Path
from huggingface_hub import snapshot_download

candidate = json.loads(Path("astra-candidate.json").read_text(encoding="utf-8"))
metadata = {
    "config.json",
    "tokenizer_config.json",
    "tokenizer.json",
    "tokenizer.model",
    "vocab.json",
    "merges.txt",
    "chat_template.jinja",
    "model.safetensors.index.json",
    "generation_config.json",
    "LICENSE",
    "README.md",
}
allowed_files = []
for filename in candidate["inventory"]:
    if filename in metadata or filename.endswith(".safetensors"):
        allowed_files.append(filename)

# Only this exact revision is downloaded; Python files are excluded.
snapshot_download(
    repo_id=candidate["source_repository"],
    revision=candidate["source_revision"],
    allow_patterns=allowed_files,
    local_dir="candidate",
)
