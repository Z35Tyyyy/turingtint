"""Download the pinned Apache-2.0 writing coach; inference stays offline."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from huggingface_hub import snapshot_download


ROOT = Path(__file__).resolve().parents[1]
MODEL = "Qwen/Qwen3-1.7B"
REVISION = "70d244cc86ccca08cf5af4e1e306ecf908b1ad5e"
FILES = ["LICENSE", "README.md", "config.json", "generation_config.json",
         "merges.txt", "tokenizer.json", "tokenizer_config.json", "vocab.json",
         "model.safetensors.index.json", "model-00001-of-00002.safetensors",
         "model-00002-of-00002.safetensors"]


def main():
    destination = ROOT / ".cache" / "coaching-model"
    snapshot_download(MODEL, revision=REVISION, local_dir=destination,
                      allow_patterns=FILES, token=False, max_workers=2)
    files = []
    for name in FILES:
        path = destination / name
        with path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        files.append({"file": name, "sha256": digest, "bytes": path.stat().st_size})
    manifest = {"model_id": MODEL, "model_revision": REVISION,
                "license": "Apache-2.0", "source": "https://huggingface.co/" + MODEL,
                "retrieved_at": datetime.now(timezone.utc).isoformat(), "files": files}
    (destination / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "installed", "model": MODEL, "revision": REVISION,
                      "bytes": sum(item["bytes"] for item in files)}))


if __name__ == "__main__":
    main()
