"""Download the pinned Apache-2.0 writing coach; inference stays offline."""
from datetime import datetime, timezone
import argparse
import hashlib
import json
from pathlib import Path
import sys

from huggingface_hub import snapshot_download


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from turingtint.coach_profiles import DEFAULT_PROFILE, PROFILES


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=tuple(PROFILES), default=DEFAULT_PROFILE)
    args = parser.parse_args()
    profile = PROFILES[args.profile]
    model, revision = profile["model_id"], profile["revision"]
    destination = ROOT / profile["directory"]
    snapshot_download(model, revision=revision, local_dir=destination,
                      allow_patterns=list(profile["files"]), token=False, max_workers=2)
    files = []
    for name in profile["files"]:
        path = destination / name
        with path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        files.append({"file": name, "sha256": digest, "bytes": path.stat().st_size})
    manifest = {"model_id": model, "model_revision": revision,
                "license": "Apache-2.0", "source": "https://huggingface.co/" + model,
                "retrieved_at": datetime.now(timezone.utc).isoformat(), "files": files}
    (destination / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "installed", "profile": args.profile, "model": model, "revision": revision,
                      "bytes": sum(item["bytes"] for item in files)}))


if __name__ == "__main__":
    main()
