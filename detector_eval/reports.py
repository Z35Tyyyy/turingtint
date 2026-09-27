"""Recompute diagnostic reports from pinned inputs and text-bound predictions."""
from __future__ import annotations

from datetime import datetime, timezone
import argparse
import json
from pathlib import Path

from .experiment import attach_scores, file_sha, load_frozen, read_jsonl, summarize_scores, write_json


def _digest_thresholds(result: dict) -> dict:
    return {name: result["thresholds"][name] for name in ("human_max", "ai_min", "selected_on", "calibration_sha256")}


def _public_result(result: dict) -> dict:
    return {"thresholds": _digest_thresholds(result), "metrics": result["metrics"],
            "gates": result["gates"], "product_approved": result["product_approved"],
            "length_subgroups": result["subgroups"].get("length_bucket", {})}


def build_comparison(root: Path) -> dict:
    from detector_models.mage import MODEL_ID, MODEL_REVISION, PREPROCESSING, verify_manifest

    frozen = root / "data/authorship/experiments/hc3-v1"
    external = root / "data/authorship/experiments/aide-v1"
    rows, manifest = load_frozen(frozen)
    external_rows, external_manifest = load_frozen(external)
    baseline_folder = root / "outputs/experiments/tfidf-v1"
    baseline_receipt = json.loads((baseline_folder / "report.json").read_text(encoding="utf-8"))["experiment"]
    for path, expected in ((frozen / "manifest.json", baseline_receipt["frozen_manifest_sha256"]),
                           (external / "manifest.json", baseline_receipt["external_manifest_sha256"]),
                           (baseline_folder / "predictions.jsonl", baseline_receipt["predictions_sha256"]),
                           (baseline_folder / "baseline.joblib", baseline_receipt["model_sha256"])):
        if file_sha(path) != expected:
            raise ValueError(f"Baseline artifact receipt mismatch: {path.name}")
    baseline_predictions = read_jsonl(baseline_folder / "predictions.jsonl")
    combined = attach_scores(rows + external_rows, baseline_predictions, hash_kind="normalized")
    split_at = len(rows)
    baseline_report = summarize_scores(combined[:split_at], combined[split_at:])
    model_dir = root / ".cache/detector-models/mage"
    model_manifest = verify_manifest(model_dir)
    if model_manifest.get("inference_allowed") is not True:
        raise ValueError("Pinned pretrained model has not completed verified conversion.")
    mage_paths = [root / "outputs/experiments/mage-hc3-v1/predictions.jsonl",
                  root / "outputs/experiments/mage-aide-v1/predictions.jsonl"]
    mage_predictions = [read_jsonl(p) for p in mage_paths]
    for predictions in mage_predictions:
        for row in predictions:
            if (row.get("model_id") != MODEL_ID or row.get("model_revision") != MODEL_REVISION
                    or row.get("preprocessing") != PREPROCESSING or row.get("max_tokens") != 512
                    or row.get("score_kind") != "uncalibrated_softmax_class_0"):
                raise ValueError("Pretrained predictions do not match the declared experiment.")
    mage_report = summarize_scores(attach_scores(rows, mage_predictions[0]), attach_scores(external_rows, mage_predictions[1]))
    summary = {"version": 1, "scope": "out-of-domain baseline comparison and external student diagnostic",
               "product_approved": False, "created_at": datetime.now(timezone.utc).isoformat(),
               "corpora": {"hc3": manifest["stats"], "aide": external_manifest["stats"]},
               "input_hashes": {"hc3": manifest["records_sha256"], "aide": external_manifest["records_sha256"],
                                "tfidf_predictions": file_sha(baseline_folder / "predictions.jsonl"),
                                "mage_hc3_predictions": file_sha(mage_paths[0]), "mage_aide_predictions": file_sha(mage_paths[1]),
                                "mage_manifest": file_sha(model_dir / "manifest.json")},
               "models": {}, "limitations": baseline_report["limitations"] + [
                   "MAGE may have seen HC3 or other benchmark text during training; no independent held-out claim for MAGE.",
                   "MAGE raw-text preprocessing and a 512-token cap differ from its upstream deployment recipe.",
                   "Neither model is installed as a user-facing authorship decision service."]}
    report_keys = ("calibrated_test", "fixed_half_test", "external_calibrated_diagnostic", "external_fixed_half_diagnostic")
    for name, report in (("tfidf_logistic", baseline_report), ("mage_raw_text_512", mage_report)):
        summary["models"][name] = {key: _public_result(report[key]) for key in report_keys}
    summary["models"]["tfidf_logistic"]["resources"] = {"training_rows": baseline_receipt["training_rows"],
                                                                      "fit_and_predict_seconds": baseline_receipt["elapsed_seconds"],
                                                                      "thread_limit": 2}
    summary["models"]["mage_raw_text_512"]["resources"] = {
        "revision": MODEL_REVISION, "max_tokens": 512, "license": model_manifest["license"],
        "truncated_hc3": sum(bool(p["truncated"]) for p in mage_predictions[0]),
        "truncated_aide": sum(bool(p["truncated"]) for p in mage_predictions[1]),
        "summed_per_record_model_forward_seconds": sum(p["batch_elapsed_ms"] for group in mage_predictions for p in group) / 1000,
        "timing_scope": "Sum of recorded forward-pass times; excludes loading/tokenization and repeats batch time for batches larger than one. This experiment used CLI batch size one.",
        "devices": sorted({p["device"] for group in mage_predictions for p in group}),
    }
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, default=Path("evaluation/results/phase2-comparison.json"))
    args = parser.parse_args()
    report = build_comparison(args.root.resolve())
    write_json(args.output, report)
    print(json.dumps({"status": "blocked", "summary": "Comparison recomputed; target-population and independence evidence are insufficient.",
                      "report": str(args.output), "product_approved": False}))


if __name__ == "__main__":
    main()
