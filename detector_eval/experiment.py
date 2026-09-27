"""Frozen, bounded, local research experiments; never enables product claims.

One deterministic excerpt per input document; linked questions and duplicate
texts stay together. Unknown authorship independence is not filled in by IDs.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import time
import unicodedata

from .metrics import FrozenThresholds, evaluate, select_thresholds

ROOT = Path(__file__).resolve().parents[1]
SEED = "turingtint-phase2-v1"
EXCERPT_POLICY = "first natural paragraph of 80-250 whitespace words; else first 250 words of document"


def sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def file_sha(path: Path) -> str:
    return sha(path.read_bytes())


def normalized(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def excerpt(text: str) -> tuple[str, str] | None:
    for part in re.split(r"\n\s*\n", text):
        if 80 <= len(part.split()) <= 250:
            return part.strip(), "natural_paragraph"
    words = list(re.finditer(r"\S+", text))
    if len(words) < 80:
        return None
    if len(words) <= 250:
        return text.strip(), "whole_short_document"
    return text[:words[249].end()].strip(), "first_250_word_excerpt_may_end_mid_sentence"


class Union:
    def __init__(self):
        self.parent: dict[str, str] = {}

    def find(self, key: str) -> str:
        self.parent.setdefault(key, key)
        if self.parent[key] != key:
            self.parent[key] = self.find(self.parent[key])
        return self.parent[key]

    def join(self, first: str, second: str) -> None:
        a, b = self.find(first), self.find(second)
        self.parent[max(a, b)] = min(a, b)


def prepare(records: list[dict], manifest: dict, *, external: bool = False) -> tuple[list[dict], dict]:
    """Freeze before scores exist; whole linked families assigned by stable hash."""
    ids: set[str] = set()
    union = Union()
    owners: dict[tuple[str, str], str] = {}
    prepared = []
    omitted = Counter()
    full_hash_labels = {}
    for row in records:
        record_id = row.get("id")
        if not isinstance(record_id, str) or not record_id or record_id in ids:
            raise ValueError("Input record IDs must be nonempty and unique.")
        ids.add(record_id)
        if row.get("label") not in {"human", "ai"} or not isinstance(row.get("text"), str):
            raise ValueError("Expected admitted human/ai text records.")
        if row.get("content_sha256") != sha(row["text"].encode()):
            raise ValueError("Record content hash does not match its text.")
        key = "record:" + record_id
        union.find(key)
        full_hash = sha(normalized(row["text"]).encode())
        if full_hash in full_hash_labels and full_hash_labels[full_hash] != row["label"]:
            raise ValueError("Identical input text has contradictory labels.")
        full_hash_labels[full_hash] = row["label"]
        for field, value in (("source_group", row.get("source_group")), ("prompt_id", row.get("prompt_id")), ("full_text", full_hash)):
            if value is not None:
                marker = (field, str(value))
                if marker in owners:
                    union.join(key, owners[marker])
                owners[marker] = key
                if field == "source_group":
                    union.join(key, "source_group:" + str(value))
        selected = excerpt(row["text"])
        if selected is None:
            omitted["too_short_" + row["label"]] += 1
            continue
        text, kind = selected
        digest = sha(normalized(text).encode())
        if ("excerpt", digest) in owners:
            union.join(key, owners[("excerpt", digest)])
        owners[("excerpt", digest)] = key
        prepared.append({"id": record_id, "text": text, "label": 1 if row["label"] == "ai" else 0,
                         "source_group": row.get("source_group"), "prompt": row.get("prompt_id"),
                         "generator": row.get("generator"), "source_dataset": row.get("source_dataset"),
                         "text_sha256": digest, "document_sha256": full_hash, "excerpt_kind": kind,
                         "word_count": len(text.split()), "length_bucket": "80-149" if len(text.split()) < 150 else "150-250"})
    for relation in manifest.get("related_source_groups", []):
        groups = relation["source_groups"]
        # Preserve absent bridge nodes: A--removed-B--C still links A and C.
        nodes = ["source_group:" + g for g in groups]
        for key in nodes[1:]:
            union.join(nodes[0], key)
    # Drop repeated excerpts and quarantine contradictory excerpt labels.
    labels = {}
    for row in prepared:
        labels.setdefault(row["text_sha256"], set()).add(row["label"])
    seen = set()
    output = []
    for row in sorted(prepared, key=lambda r: r["id"]):
        digest = row["text_sha256"]
        if len(labels[digest]) > 1:
            omitted["conflicting_excerpt"] += 1
            continue
        if digest in seen:
            omitted["duplicate_excerpt"] += 1
            continue
        seen.add(digest)
        unit = sha(union.find("record:" + row["id"]).encode())
        draw = int(sha((SEED + ":" + unit).encode())[:16], 16) / 2**64
        row["split_unit"] = unit
        row["split"] = "external" if external else "train" if draw < .6 else "calibration" if draw < .8 else "test"
        output.append(row)
    if not output:
        raise ValueError("No usable excerpts remain.")
    return output, {"omitted": dict(omitted), "counts": dict(Counter(f"{r['split']}:{r['label']}" for r in output)),
                    "split_units": len({r["split_unit"] for r in output}), "excerpt_kinds": dict(Counter(r["excerpt_kind"] for r in output))}


def freeze(input_dir: Path, output_dir: Path, *, external: bool = False) -> dict:
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError("Frozen experiment directory is already populated; use a new version.")
    manifest = json.loads((input_dir / "manifest.json").read_text(encoding="utf-8"))
    source = input_dir / "records.jsonl"
    if file_sha(source) != manifest["records_sha256"]:
        raise ValueError("Acquisition manifest does not match records.")
    rows, stats = prepare(read_jsonl(source), manifest, external=external)
    output_dir.mkdir(parents=True, exist_ok=True)
    destination = output_dir / "records.jsonl"
    destination.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    receipt = {"version": 1, "created_at": datetime.now(timezone.utc).isoformat(), "seed": SEED,
               "source_dataset": manifest["source_dataset"], "source_records_sha256": file_sha(source),
               "source_manifest_sha256": file_sha(input_dir / "manifest.json"), "records_sha256": file_sha(destination),
               "split_policy": "external only" if external else "60/20/20 stable-hash linked source/prompt/exact-text components",
               "excerpt_policy": EXCERPT_POLICY, "scope": "engineering diagnostic; not independent academic validation",
               "license_id": manifest["license_id"], "attribution": manifest["attribution"],
               "source_limitations": manifest["limitations"], "stats": stats,
               "code_sha256": file_sha(Path(__file__)), "independent_authors_verified": False,
               "near_duplicate_independence_verified": False}
    write_json(output_dir / "manifest.json", receipt)
    return receipt


def load_frozen(folder: Path) -> tuple[list[dict], dict]:
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    if file_sha(folder / "records.jsonl") != manifest["records_sha256"]:
        raise ValueError("Frozen records changed after acquisition.")
    rows = read_jsonl(folder / "records.jsonl")
    for field in ("id", "split_unit", "source_group", "prompt", "text_sha256", "document_sha256"):
        locations = {}
        for row in rows:
            value = row.get(field)
            if value is not None:
                if value in locations and locations[value] != row["split"]:
                    raise ValueError(f"Cross-split leakage through {field}.")
                locations[value] = row["split"]
    return rows, manifest


def attach_scores(rows: list[dict], predictions: list[dict], *, hash_kind: str = "raw") -> list[dict]:
    if hash_kind not in {"raw", "normalized"}:
        raise ValueError("Specify raw or normalized prediction text hashes.")
    by_id = {}
    for prediction in predictions:
        if prediction["id"] in by_id:
            raise ValueError("Duplicate prediction ID.")
        by_id[prediction["id"]] = prediction
    if set(by_id) != {r["id"] for r in rows}:
        raise ValueError("Predictions must cover exactly the frozen IDs.")
    for row in rows:
        expected = sha(row["text"].encode()) if hash_kind == "raw" else row["text_sha256"]
        if by_id[row["id"]].get("text_sha256") != expected:
            raise ValueError("Prediction text hash does not match the frozen excerpt.")
    return [{**r, "score": by_id[r["id"]]["score_ai"]} for r in rows]


def summarize_scores(rows: list[dict], external_rows: list[dict] | None = None) -> dict:
    calibration = [r for r in rows if r["split"] == "calibration"]
    test = [r for r in rows if r["split"] == "test"]
    thresholds = select_thresholds(calibration)
    # .5 is predeclared diagnostic, not upstream MAGE deployment threshold.
    fixed = FrozenThresholds(human_max=.49999999999999994, ai_min=.5)
    result = {"calibrated_test": evaluate(test, thresholds, require_prompt_disjoint=True),
              # Split disjointness was checked above using actual calibration
              # provenance. A predefined diagnostic has no calibration metadata.
              "fixed_half_test": evaluate(test, fixed)}
    if external_rows is not None:
        known_hashes = {r["document_sha256"] for r in rows} | {r["text_sha256"] for r in rows}
        if any(r["document_sha256"] in known_hashes or r["text_sha256"] in known_hashes for r in external_rows):
            raise ValueError("External corpus overlaps the training/calibration/test corpus.")
        # Development scope: target corpus has three AI records and unknown families.
        external = [{**r, "split": "development"} for r in external_rows]
        result["external_calibrated_diagnostic"] = evaluate(external, thresholds, split="development")
        result["external_fixed_half_diagnostic"] = evaluate(external, fixed, split="development")
    result["product_approved"] = False
    result["limitations"] = ["HC3 is Wikipedia QA, not English student writing.",
                              "AIDE has only three AI essays and unknown author/generator identities.",
                              "Model pretraining overlap, author independence and near-duplicate independence are unverified.",
                              "One excerpt per document; clipped excerpts are not sentence localization evidence.",
                              "Raw scores and selected thresholds are not calibrated authorship probabilities.",
                              "Fixed half threshold is a diagnostic convention, not the upstream MAGE decision rule."]
    return result


def train_baseline(frozen: Path, external: Path, output: Path) -> dict:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.pipeline import FeatureUnion, Pipeline
    from sklearn.linear_model import LogisticRegression
    from threadpoolctl import threadpool_limits
    import joblib
    import sklearn

    if output.exists() and any(output.iterdir()):
        raise ValueError("Experiment output already exists; use a new version.")
    rows, manifest = load_frozen(frozen)
    external_rows, external_manifest = load_frozen(external)
    train = [r for r in rows if r["split"] == "train"]
    if Counter(r["label"] for r in train).keys() != {0, 1}:
        raise ValueError("Training requires both classes.")
    model = Pipeline([("features", FeatureUnion([
        ("word", TfidfVectorizer(ngram_range=(1, 2), min_df=2, max_features=20_000, sublinear_tf=True)),
        ("char", TfidfVectorizer(analyzer="char", ngram_range=(3, 5), min_df=3, max_features=40_000, sublinear_tf=True))])),
        ("classifier", LogisticRegression(C=1.0, class_weight="balanced", solver="liblinear", max_iter=500, random_state=42))])
    started = time.perf_counter()
    with threadpool_limits(limits=2):
        model.fit([r["text"] for r in train], [r["label"] for r in train])
        position = list(model.classes_).index(1)
        predictions = model.predict_proba([r["text"] for r in rows])[:, position]
        external_predictions = model.predict_proba([r["text"] for r in external_rows])[:, position]
    elapsed = time.perf_counter() - started
    scored = [{**r, "score": float(p)} for r, p in zip(rows, predictions)]
    scored_external = [{**r, "score": float(p)} for r, p in zip(external_rows, external_predictions)]
    report = summarize_scores(scored, scored_external)
    output.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, output / "baseline.joblib")
    (output / "predictions.jsonl").write_text("".join(json.dumps({"id": r["id"], "score_ai": r["score"], "split": r["split"], "text_sha256": r["text_sha256"]}) + "\n" for r in scored + scored_external), encoding="utf-8")
    report["experiment"] = {"model": "TF-IDF word1-2/char3-5 + balanced logistic C1", "sklearn": sklearn.__version__,
                            "training_rows": len(train), "elapsed_seconds": elapsed, "thread_limit": 2,
                            "features_fit_on": "train only", "hyperparameter_search": False,
                            "frozen_manifest_sha256": file_sha(frozen / "manifest.json"),
                            "external_manifest_sha256": file_sha(external / "manifest.json"),
                            "model_sha256": file_sha(output / "baseline.joblib"),
                            "predictions_sha256": file_sha(output / "predictions.jsonl"),
                            "code_sha256": file_sha(Path(__file__)), "data": manifest["stats"], "external_data": external_manifest["stats"]}
    write_json(output / "report.json", report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prepare_parser = commands.add_parser("freeze")
    prepare_parser.add_argument("--input", required=True, type=Path)
    prepare_parser.add_argument("--output", required=True, type=Path)
    prepare_parser.add_argument("--external", action="store_true")
    train_parser = commands.add_parser("baseline")
    train_parser.add_argument("--frozen", required=True, type=Path)
    train_parser.add_argument("--external", required=True, type=Path)
    train_parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = freeze(args.input, args.output, external=args.external) if args.command == "freeze" else train_baseline(args.frozen, args.external, args.output)
    print(json.dumps(result.get("experiment", result), ensure_ascii=False))


if __name__ == "__main__":
    main()
