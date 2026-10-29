import json
from huggingface_hub import snapshot_download

candidate = json.load(open("astra-candidate.json", encoding="utf-8"))
metadata = {"config.json", "tokenizer_config.json", "tokenizer.json",
            "tokenizer.model", "vocab.json", "merges.txt", "chat_template.jinja",
            "model.safetensors.index.json", "generation_config.json", "LICENSE", "README.md"}
allowed = [p for p in candidate["inventory"]
           if p in metadata or p.endswith(".safetensors")]
snapshot_download(repo_id=candidate["source_repository"],
                  revision=candidate["source_revision"],
                  allow_patterns=allowed, local_dir="candidate")
