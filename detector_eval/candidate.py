"""CPU-only policy diagnostics over immutable phase-2 prediction artifacts.

Freeze selects a MAGE score representation using calibration rows only. Diagnose
requires the exact frozen selection before reading/evaluating the test/external
policies. This is retrospective development work, not a new blind benchmark.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path

from .experiment import attach_scores, file_sha, load_frozen, read_jsonl
from .metrics import auroc, select_thresholds

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = Path("evaluation/results/candidate-diagnostic.json")
KINDS = ("float32_softmax", "class0_logit", "logit_margin")
UPSTREAM_LOGIT_CUTOFF = 3.08583984375
SCORE_RECIPE = {"version": 1, "source": "raw_logits_ai_class_0_minus_human_class_1",
                "transform": "python_float64_stable_sigmoid", "preprocessing": "raw_text_v1",
                "max_tokens": 512, "legacy_float32_softmax_used_for_decision": False}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def sigmoid(value):
    if not math.isfinite(value):
        raise ValueError("Nonfinite model logit")
    return 1 / (1 + math.exp(-value)) if value >= 0 else math.exp(value) / (1 + math.exp(value))


def score(prediction, kind):
    values = prediction.get("raw_logits")
    if not isinstance(values, list) or len(values) != 2 or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in values):
        raise ValueError("Expected two finite saved logits")
    if kind == "float32_softmax":
        result = prediction["score_ai"]
        if isinstance(result, bool) or not isinstance(result, (int, float)) or not math.isfinite(result) or not 0 <= result <= 1:
            raise ValueError("Invalid saved softmax")
        return result
    if kind == "class0_logit":
        return sigmoid(values[0])
    if kind == "logit_margin":
        return sigmoid(values[0] - values[1])
    raise ValueError("Unknown score representation")


def load_dataset(root, name, reference):
    folder = root / f"data/authorship/experiments/{name}-v1"
    rows, manifest = load_frozen(folder)
    path = root / f"outputs/experiments/mage-{name}-v1/predictions.jsonl"
    if manifest["records_sha256"] != reference["input_hashes"][name] or file_sha(path) != reference["input_hashes"][f"mage_{name}_predictions"]:
        raise ValueError("Frozen phase-2 artifact changed")
    predictions = read_jsonl(path)
    attach_scores(rows, predictions)  # rejects duplicate IDs and stale text hashes
    for item in predictions:
        if item["preprocessing"] != "raw_text_v1" or item["max_tokens"] != 512 or item["truncated"]:
            raise ValueError("This diagnostic requires complete raw-text 512-token records")
        score(item, "logit_margin")
    return rows, {item["id"]: item for item in predictions}


def metrics(rows, decisions, scores=None):
    if len(rows) != len(decisions) or any(value not in {"ai", "human", "uncertain"} for value in decisions):
        raise ValueError("Decision inventory mismatch")
    c = Counter((row["label"], decision) for row, decision in zip(rows, decisions))
    human = sum(row["label"] == 0 for row in rows)
    ai = len(rows) - human
    answered = sum(decision != "uncertain" for decision in decisions)
    ratio = lambda a, b: a / b if b else None
    result = {"records": len(rows), "human": human, "ai": ai,
              "confusion": {"tp": c[1, "ai"], "fp": c[0, "ai"], "tn": c[0, "human"], "fn": c[1, "human"],
                            "abstain_human": c[0, "uncertain"], "abstain_ai": c[1, "uncertain"]},
              "answered": answered, "coverage": ratio(answered, len(rows)),
              "human_fpr": ratio(c[0, "ai"], human), "ai_recall": ratio(c[1, "ai"], ai),
              "false_human_rate": ratio(c[1, "human"], ai),
              "answered_human_fpr": ratio(c[0, "ai"], c[0, "ai"] + c[0, "human"]),
              "human_coverage": ratio(c[0, "ai"] + c[0, "human"], human),
              "ai_coverage": ratio(c[1, "ai"] + c[1, "human"], ai)}
    if scores is not None:
        result["ranking_auroc"] = auroc([row["label"] for row in rows], scores)
    return result


def select_on_calibration(rows, predictions):
    if not rows or any(row["split"] != "calibration" for row in rows):
        raise ValueError("Candidate selection accepts calibration rows only")
    candidates, thresholds = {}, {}
    for kind in KINDS:
        scored = [{**row, "score": score(predictions[row["id"]], kind)} for row in rows]
        threshold = select_thresholds(scored, ai_false_positive_cap=.01, human_false_positive_cap=.01)
        thresholds[kind] = threshold
        result = metrics(scored, [threshold.predict(row["score"]) for row in scored], [row["score"] for row in scored])
        native = {}
        if kind != "float32_softmax":
            for field in ("human_max", "ai_min"):
                cutoff = getattr(threshold, field)
                matching = [row for row in scored if row["score"] == cutoff]
                if not matching:
                    native[field] = None
                else:
                    values = predictions[matching[0]["id"]]["raw_logits"]
                    native[field] = values[0] if kind == "class0_logit" else values[0] - values[1]
        candidates[kind] = {"thresholds": {key: threshold.to_dict()[key] for key in
                            ("human_max", "ai_min", "selected_on", "calibration_sha256", "ai_false_positive_cap", "human_false_positive_cap")},
                            "native_logit_thresholds": native, "calibration_metrics": result,
                            "distinct_calibration_scores": len({row["score"] for row in scored})}
    # Fixed selection rule: AI recall first, coverage second; ties prefer the
    # logit margin, then class0, then the rounded saved softmax. No test outcomes.
    chosen = max(KINDS, key=lambda kind: (candidates[kind]["calibration_metrics"]["ai_recall"],
                                        candidates[kind]["calibration_metrics"]["coverage"], KINDS.index(kind)))
    selection = {"selected_on": "hc3_calibration_only", "selected_candidate": chosen,
                 "rule": "Maximum calibration AI recall, then coverage, under separate empirical 1% class-error caps; ties prefer margin then class0 then saved softmax.",
                 "caps_are_empirical_not_confidence_guarantees": True, "candidates": candidates,
                 "calibration_records_sha256": digest([{key: row[key] for key in ("id", "label", "text_sha256", "source_group")} for row in rows])}
    selection["selection_sha256"] = digest(selection)
    return selection, thresholds


def threshold_decision(value, config):
    if config["ai_min"] is not None and value >= config["ai_min"]:
        return "ai"
    if config["human_max"] is not None and value <= config["human_max"]:
        return "human"
    return "uncertain"


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def run(root, output, phase):
    reference = json.loads((root / "evaluation/results/phase2-comparison.json").read_text(encoding="utf-8"))
    rows, mage = load_dataset(root, "hc3", reference)
    calibration = [row for row in rows if row["split"] == "calibration"]
    selection, thresholds = select_on_calibration(calibration, mage)
    if output.exists():
        report = json.loads(output.read_text(encoding="utf-8"))
        if report["selection"]["selection_sha256"] != selection["selection_sha256"]:
            raise ValueError("Selection differs from the existing frozen diagnostic")
    elif phase == "diagnose":
        raise ValueError("Run freeze before diagnose")
    else:
        report = {"version": 1, "phase": "calibration_frozen", "product_approved": False,
                  "frozen_at": datetime.now(timezone.utc).isoformat(), "selection": selection,
                  "input_hashes": reference["input_hashes"],
                  "limitations": ["All benchmark artifacts were previously examined; these are retrospective development diagnostics, not an independent blind validation.",
                                  "Only the declared HC3 calibration split selected the new score representation and thresholds; current test/external outcomes cannot change the frozen selection.",
                                  "HC3 may overlap pretrained MAGE training. AIDE has only 3 AI examples and lacks verified independent-author groups.",
                                  "No model was retrained and no new inference was run. Saved raw logits came from float16 CUDA inference; sigmoid is recomputed in Python double precision.",
                                  "These are excerpt-level decisions on complete 80-250-word records, not mixed/sentence localization or multi-block passage validation.",
                                  "Upstream fixed-logit rule on raw text is only a mismatch diagnostic; upstream cleaning was not evaluated here."]}
    if phase == "freeze":
        report["score_recipe"] = SCORE_RECIPE
        write(output, report)
        return report

    external, external_mage = load_dataset(root, "aide", reference)
    baseline_path = root / "outputs/experiments/tfidf-v1/predictions.jsonl"
    if file_sha(baseline_path) != reference["input_hashes"]["tfidf_predictions"]:
        raise ValueError("Frozen baseline predictions changed")
    baseline = read_jsonl(baseline_path)
    attach_scores(rows + external, baseline, hash_kind="normalized")
    baseline = {row["id"]: row for row in baseline}
    mage.update(external_mage)
    old_mage = reference["models"]["mage_raw_text_512"]["calibrated_test"]["thresholds"]
    old_baseline = reference["models"]["tfidf_logistic"]["calibrated_test"]["thresholds"]
    chosen = selection["selected_candidate"]
    report["diagnostics"] = {}
    for name, subset in (("calibration", calibration), ("hc3_test_retrospective", [row for row in rows if row["split"] == "test"]), ("aide_external_retrospective", external)):
        mage_decisions = [threshold_decision(mage[row["id"]]["score_ai"], old_mage) for row in subset]
        baseline_decisions = [threshold_decision(baseline[row["id"]]["score_ai"], old_baseline) for row in subset]
        candidate_scores = [score(mage[row["id"]], chosen) for row in subset]
        policies = {"current_mandatory_agreement": [a if a == b else "uncertain" for a, b in zip(mage_decisions, baseline_decisions)],
                    "existing_mage_only": mage_decisions, "existing_tfidf_only": baseline_decisions,
                    "frozen_primary_mage_candidate": [thresholds[chosen].predict(value) for value in candidate_scores],
                    "upstream_fixed_logit_on_raw_text_mismatch": ["ai" if mage[row["id"]]["raw_logits"][0] > UPSTREAM_LOGIT_CUTOFF else "human" for row in subset]}
        report["diagnostics"][name] = {policy: metrics(subset, decisions, candidate_scores if policy == "frozen_primary_mage_candidate" else None) for policy, decisions in policies.items()}
    report.update(phase="retrospective_diagnostics_complete", score_recipe=SCORE_RECIPE,
                  diagnosed_at=datetime.now(timezone.utc).isoformat())
    write(output, report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("freeze", "diagnose"))
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    root = args.root.resolve()
    report = run(root, root / args.output, args.phase)
    print(json.dumps({"phase": report["phase"], "selected_candidate": report["selection"]["selected_candidate"],
                      "selection_sha256": report["selection"]["selection_sha256"], "output": str(args.output)}))


if __name__ == "__main__":
    main()
