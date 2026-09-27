"""Pinned, local-only inference adapter for the official MAGE Longformer.

The downloaded upstream deployment source is preserved as non-executable audit
evidence. Inference uses installed Transformers implementation, never repository
code. Scores are uncalibrated model outputs, not verified authorship probability.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import time
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MODEL_DIR = ROOT / ".cache" / "detector-models" / "mage"
MODEL_ID = "yaful/MAGE"
MODEL_REVISION = "0d82ca0fdf6ebef5babb813cc11bd8eb2552c846"
SOURCE_REVISION = "6d11f851184b9f04166f952ddc1f47727f36710f"
WEIGHTS_SHA256 = "faa61e5c1947367058280e5317b32fbf7b6335e7f4c12c34b4f34c83ad56b359"
MAX_DOWNLOAD_BYTES = 2_000_000_000
FILES = ("README.md", "config.json", "merges.txt", "pytorch_model.bin", "special_tokens_map.json",
         "tokenizer.json", "tokenizer_config.json", "vocab.json")
# Captured from the immutable official release after Git-blob/LFS verification.
# Manifest contents alone must never be allowed to redefine this model's bytes.
PINNED_ARTIFACTS = {
    "README.md": "6e4d7f4bdc9181eba6fea22fdfe9cfd16116179c90d6222d98ea572e22067c1a",
    "config.json": "81eeb8706ba6150c1472434974882e5ec5daf6bf54977cff86fb66062f0d0ad2",
    "merges.txt": "1ce1664773c50f3e0cc8842619a93edc4624525b728b188a9e0be33b7726adc5",
    "pytorch_model.bin": WEIGHTS_SHA256,
    "special_tokens_map.json": "06e405a36dfe4b9604f484f6a1e619af1a7f7d09e34a8555eb0b77b66318067f",
    "tokenizer.json": "5e158a6340357dc1ce64d776ac6618e6645909e28604d87619dd9c92a7e1a623",
    "tokenizer_config.json": "4e95efbbb4595f9a11496fe8b3bd2c0cdfab422ff990373d3799780ddc6e1e6c",
    "vocab.json": "ed19656ea1707df69134c4af35c8ceda2cc9860bf2c3495026153a133670ab5e",
    "LICENSE-upstream.txt": "c71d239df91726fc519c6eb72d318ec65820627232b2f796219e87dcf35d0ab4",
    "upstream-README.txt": "cf66f27db6326bf34be3fbda78379edb37f1a151b9b133d349ca8d41558f435f",
    "upstream-deployment.txt": "64791a5c776ad56e2896ffd51c351c806db3cb35bd66194b3b933eba19625cec",
}
CANONICAL_SAFE_HASH = "7c14d683937626c32419f083a07e4350353b60e58d00b9cebfeed0c4a6b78ebd"
SOURCE_BASE = f"https://raw.githubusercontent.com/yafuly/MAGE/{SOURCE_REVISION}"
AI_CLASS = 0
HUMAN_CLASS = 1
PREPROCESSING = "raw_text_v1"


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _get_json(url: str) -> dict:
    request = Request(url, headers={"User-Agent": "TuringTint-open-research/0.1"})
    with urlopen(request, timeout=60) as response:
        payload = response.read(5_000_001)
    if len(payload) > 5_000_000:
        raise ValueError("Unexpectedly large repository metadata response.")
    return json.loads(payload)


def _download(url: str, destination: Path, expected_size: int | None = None,
              expected_sha256: str | None = None, expected_git_blob: str | None = None) -> dict:
    if expected_size is not None and expected_size > MAX_DOWNLOAD_BYTES:
        raise ValueError("An artifact exceeds the download budget.")
    if destination.is_file():
        actual_hash = sha256_file(destination)
        reusable = expected_sha256 and actual_hash == expected_sha256
        if expected_git_blob:
            raw = destination.read_bytes()
            reusable = hashlib.sha1(f"blob {len(raw)}\0".encode() + raw).hexdigest() == expected_git_blob
        if reusable:
            return {"file": destination.name, "bytes": destination.stat().st_size, "sha256": actual_hash,
                    "url": url, "verified": True}
    partial = destination.with_name(destination.name + ".download")
    request = Request(url, headers={"User-Agent": "TuringTint-open-research/0.1"})
    digest = hashlib.sha256()
    received = 0
    last_report = time.monotonic()
    with urlopen(request, timeout=60) as response, partial.open("wb") as stream:
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            received += len(chunk)
            if received > (expected_size if expected_size is not None else 1_000_000):
                raise ValueError(f"Artifact {destination.name} exceeds its declared size.")
            stream.write(chunk)
            digest.update(chunk)
            if time.monotonic() - last_report >= 10:
                print(json.dumps({"event": "download_progress", "file": destination.name, "bytes": received}), flush=True)
                last_report = time.monotonic()
    if expected_size is not None and received != expected_size:
        raise ValueError(f"Artifact size mismatch: {destination.name}.")
    actual_hash = digest.hexdigest()
    if expected_sha256 and actual_hash != expected_sha256:
        raise ValueError(f"Artifact checksum mismatch: {destination.name}.")
    if expected_git_blob:
        raw = partial.read_bytes()
        if hashlib.sha1(f"blob {len(raw)}\0".encode() + raw).hexdigest() != expected_git_blob:
            raise ValueError(f"Git blob checksum mismatch: {destination.name}.")
    partial.replace(destination)
    return {"file": destination.name, "bytes": received, "sha256": actual_hash, "url": url, "verified": True}


def download_model(model_dir: str | Path = DEFAULT_MODEL_DIR) -> dict:
    """Acquire only an immutable official model and human-readable evidence."""
    directory = Path(model_dir)
    directory.mkdir(parents=True, exist_ok=True)
    info = _get_json(f"https://huggingface.co/api/models/{MODEL_ID}/revision/{MODEL_REVISION}?blobs=true")
    if info.get("sha") != MODEL_REVISION or info.get("cardData", {}).get("license") != "apache-2.0":
        raise ValueError("Official repository revision/license verification failed.")
    siblings = {entry["rfilename"]: entry for entry in info["siblings"]}
    total = sum(siblings[name]["size"] for name in FILES)
    if total > MAX_DOWNLOAD_BYTES:
        raise ValueError("Pinned artifacts exceed the 2 GB initial download budget.")
    if siblings["pytorch_model.bin"].get("lfs", {}).get("sha256") != WEIGHTS_SHA256:
        raise ValueError("The pinned checkpoint checksum differs from the audited value.")
    files = []
    for name in FILES:
        entry = siblings[name]
        files.append(_download(
            f"https://huggingface.co/{MODEL_ID}/resolve/{MODEL_REVISION}/{name}", directory / name,
            expected_size=entry["size"], expected_sha256=entry.get("lfs", {}).get("sha256"),
            expected_git_blob=None if "lfs" in entry else entry["blobId"],
        ))
    # These are documentary evidence, never imported or evaluated as Python.
    for remote, local in (("LICENSE", "LICENSE-upstream.txt"), ("README.md", "upstream-README.txt"),
                          ("deployment/utils.py", "upstream-deployment.txt")):
        files.append(_download(f"{SOURCE_BASE}/{remote}", directory / local))
    upstream = (directory / "upstream-deployment.txt").read_text(encoding="utf-8")
    if not re.search(r'0\s*:\s*"machine-generated"', upstream) or not re.search(r'1\s*:\s*"human-written"', upstream):
        raise ValueError("Label mapping evidence does not match the audited upstream source.")
    manifest = {
        "schema_version": 1, "model_id": MODEL_ID, "model_revision": MODEL_REVISION,
        "source_revision": SOURCE_REVISION, "license": "Apache-2.0",
        "license_source": f"https://huggingface.co/{MODEL_ID}/blob/{MODEL_REVISION}/README.md",
        "source_license": f"{SOURCE_BASE}/LICENSE", "label_mapping": {"0": "ai", "1": "human"},
        "label_mapping_evidence": f"{SOURCE_BASE}/deployment/utils.py",
        "downloaded_at": datetime.now(timezone.utc).isoformat(), "download_bytes": sum(f["bytes"] for f in files),
        "files": files, "inference_allowed": False,
        "notes": ["Only the restricted weights-only loader may convert the upstream .bin checkpoint.",
                  "Model outputs have not been validated or calibrated for this product.",
                  "The default raw-text preprocessing differs from the upstream recommended cleaning pipeline."],
    }
    (directory / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return manifest


def _torch_version_tuple(version: str) -> tuple[int, int, int]:
    match = re.match(r"(\d+)\.(\d+)\.(\d+)", version)
    if not match:
        raise ValueError("Could not verify the installed PyTorch version.")
    return tuple(int(part) for part in match.groups())


def verify_manifest(model_dir: str | Path, *, verify_derived: bool = True) -> dict:
    directory = Path(model_dir)
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    if (manifest.get("model_id") != MODEL_ID or manifest.get("model_revision") != MODEL_REVISION
            or manifest.get("source_revision") != SOURCE_REVISION
            or manifest.get("license") != "Apache-2.0"
            or manifest.get("label_mapping") != {"0": "ai", "1": "human"}):
        raise ValueError("Model manifest does not match the pinned research adapter.")
    entries = manifest.get("files", [])
    names = [entry.get("file") for entry in entries]
    expected_names = set(PINNED_ARTIFACTS)
    if manifest.get("inference_allowed") is True:
        expected_names.add("model.safetensors")
    if len(names) != len(set(names)) or set(names) != expected_names:
        raise ValueError("The manifest must contain every pinned artifact exactly once, with no unlisted substitutions.")
    for entry in entries:
        name = entry["file"]
        if Path(name).name != name or not name or name in {".", ".."}:
            raise ValueError("Unsafe path in model manifest.")
        path = directory / name
        if path.is_symlink():
            raise ValueError("Model artifacts must be regular files within the verified cache.")
        if not path.is_file() or path.stat().st_size != entry["bytes"]:
            raise ValueError(f"Missing or incorrect model artifact: {name}.")
        if name == "model.safetensors":
            if entry.get("derived_from_sha256") != WEIGHTS_SHA256:
                raise ValueError("Converted weights are not bound to the pinned upstream checkpoint.")
            if not verify_derived:
                continue
            expected_hash = CANONICAL_SAFE_HASH
        else:
            expected_hash = PINNED_ARTIFACTS[name]
        if entry.get("sha256") != expected_hash or sha256_file(path) != expected_hash:
            raise ValueError(f"Model checksum mismatch: {name}.")
    return manifest


def _canonicalize_safetensors(path: Path) -> None:
    """Sort the JSON header so serialization metadata ordering cannot change hashes."""
    temporary = path.with_name(path.name + ".canonical")
    with path.open("rb") as source:
        header_size = int.from_bytes(source.read(8), "little")
        if not 0 < header_size < 1_000_000:
            raise ValueError("Invalid safetensors header size.")
        header = json.loads(source.read(header_size))
        encoded = json.dumps(header, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        encoded += b" " * (-len(encoded) % 8)
        with temporary.open("wb") as target:
            target.write(len(encoded).to_bytes(8, "little"))
            target.write(encoded)
            shutil.copyfileobj(source, target, length=1024 * 1024)
    temporary.replace(path)


def convert_to_safetensors(model_dir: str | Path = DEFAULT_MODEL_DIR) -> dict:
    """Convert once using patched PyTorch's restricted loader; never unpickle code."""
    import torch
    from safetensors.torch import save_file

    if _torch_version_tuple(torch.__version__) < (2, 6, 0):
        raise RuntimeError("PyTorch >=2.6.0 is required for the restricted checkpoint conversion.")
    directory = Path(model_dir)
    manifest = verify_manifest(directory, verify_derived=False)
    binary = directory / "pytorch_model.bin"
    if sha256_file(binary) != WEIGHTS_SHA256:
        raise ValueError("Refusing to load an unverified checkpoint.")
    state = torch.load(binary, map_location="cpu", weights_only=True, mmap=True)
    if not isinstance(state, dict) or not state or not all(isinstance(key, str) and isinstance(value, torch.Tensor) for key, value in state.items()):
        raise ValueError("Checkpoint is not a plain tensor state dictionary.")
    weights = directory / "model.safetensors"
    pending = directory / "model.safetensors.converting"
    save_file({key: state[key].contiguous() for key in sorted(state)}, str(pending),
              metadata={"format": "pt", "source_model": MODEL_ID, "source_revision": MODEL_REVISION})
    _canonicalize_safetensors(pending)
    if sha256_file(pending) != CANONICAL_SAFE_HASH:
        raise ValueError("The converted tensor artifact differs from the independently pinned canonical conversion.")
    pending.replace(weights)
    entry = {"file": weights.name, "bytes": weights.stat().st_size, "sha256": sha256_file(weights),
             "derived_from_sha256": WEIGHTS_SHA256, "conversion": "torch.load(weights_only=True,mmap=True); safetensors.save_file"}
    manifest["files"] = [item for item in manifest["files"] if item["file"] != weights.name] + [entry]
    manifest["conversion"] = {"torch_version": torch.__version__, "converted_at": datetime.now(timezone.utc).isoformat()}
    manifest["inference_allowed"] = True
    (directory / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return manifest


def validate_records(records: list[dict]) -> list[dict]:
    seen = set()
    for record in records:
        if not isinstance(record, dict) or not isinstance(record.get("id"), str) or not 1 <= len(record["id"]) <= 256:
            raise ValueError("Each record needs a string id containing 1–256 characters.")
        if record["id"] in seen:
            raise ValueError(f"Duplicate input id: {record['id']}.")
        seen.add(record["id"])
        if not isinstance(record.get("text"), str) or not record["text"].strip() or len(record["text"]) > 200_000:
            raise ValueError("Each record needs 1–200,000 text characters.")
        if any(0xD800 <= ord(character) <= 0xDFFF for character in record["text"]):
            raise ValueError("Record text contains invalid Unicode surrogate characters.")
    return records


class MageDetector:
    """Reusable research predictor. Loading and prediction make no network calls."""

    def __init__(self, model_dir: str | Path = DEFAULT_MODEL_DIR, *, device: str = "auto", max_tokens: int = 1024):
        import torch
        from transformers import AutoConfig, AutoModelForSequenceClassification, AutoTokenizer

        if not 16 <= max_tokens <= 4096:
            raise ValueError("max_tokens must be between 16 and 4096 inclusive.")
        if device not in {"auto", "cpu", "cuda"}:
            raise ValueError("device must be auto, cpu, or cuda.")
        self.directory = Path(model_dir)
        self.manifest = verify_manifest(self.directory)
        if not self.manifest.get("inference_allowed") or not (self.directory / "model.safetensors").is_file():
            raise ValueError("Convert the verified checkpoint to safetensors before inference.")
        self.device = "cuda" if (device == "auto" and torch.cuda.is_available()) else "cpu" if device == "auto" else device
        if self.device == "cuda" and not torch.cuda.is_available():
            raise ValueError("CUDA was requested but is unavailable.")
        self.max_tokens = max_tokens
        self.dtype = torch.float16 if self.device == "cuda" else torch.float32
        config = AutoConfig.from_pretrained(self.directory, local_files_only=True, trust_remote_code=False)
        if config.model_type != "longformer" or config.num_labels != 2 or getattr(config, "auto_map", None):
            raise ValueError("Unexpected model architecture or label count.")
        self.tokenizer = AutoTokenizer.from_pretrained(self.directory, local_files_only=True, trust_remote_code=False)
        self.model = AutoModelForSequenceClassification.from_pretrained(
            self.directory, config=config, local_files_only=True, trust_remote_code=False,
            use_safetensors=True, dtype=self.dtype,
        ).to(self.device).eval()
        self.torch = torch

    def predict(self, records: list[dict], *, batch_size: int = 1) -> list[dict]:
        validate_records(records)
        if not 1 <= batch_size <= 4:
            raise ValueError("batch_size must be between 1 and 4 for the local memory budget.")
        predictions = []
        for first in range(0, len(records), batch_size):
            batch = records[first:first + batch_size]
            texts = [record["text"] for record in batch]
            counts = [len(self.tokenizer(text, truncation=False, add_special_tokens=True)["input_ids"]) for text in texts]
            encoded = self.tokenizer(texts, padding=True, truncation=True, max_length=self.max_tokens, return_tensors="pt")
            actual_counts = encoded["attention_mask"].sum(dim=1).tolist()
            encoded = {name: tensor.to(self.device) for name, tensor in encoded.items()}
            # Longformer sequence classification uses global attention on CLS.
            global_attention = self.torch.zeros_like(encoded["input_ids"])
            global_attention[:, 0] = 1
            started = time.perf_counter()
            with self.torch.inference_mode():
                logits = self.model(**encoded, global_attention_mask=global_attention).logits.float()
                scores = self.torch.softmax(logits, dim=-1)[:, AI_CLASS].cpu().tolist()
                raw_logits = logits.cpu().tolist()
            elapsed = (time.perf_counter() - started) * 1000
            for index, record in enumerate(batch):
                score = scores[index]
                if not math.isfinite(score) or not 0 <= score <= 1:
                    raise RuntimeError("The model produced a non-finite or invalid score.")
                predictions.append({
                    "id": record["id"], "score_ai": score, "raw_logits": raw_logits[index],
                    "text_sha256": hashlib.sha256(record["text"].encode("utf-8")).hexdigest(),
                    "input_characters": len(record["text"]),
                    "score_kind": "uncalibrated_softmax_class_0", "model_id": MODEL_ID,
                    "model_revision": MODEL_REVISION, "source_revision": SOURCE_REVISION,
                    "preprocessing": PREPROCESSING, "original_tokens": counts[index],
                    "input_tokens": int(actual_counts[index]), "max_tokens": self.max_tokens,
                    "truncated": counts[index] > self.max_tokens, "device": self.device,
                    "dtype": str(self.dtype), "batch_elapsed_ms": round(elapsed, 3),
                    "peak_cuda_allocated_mib": (round(self.torch.cuda.max_memory_allocated() / 1024 ** 2, 1)
                                                if self.device == "cuda" else None),
                    "calibrated": False, "product_approved": False,
                })
        return predictions
