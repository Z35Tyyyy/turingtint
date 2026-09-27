"""Recompute real diagnostic metrics; this experiment cannot unlock authorship."""
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from detector_eval.reports import build_comparison


if __name__ == "__main__":
    try:
        report = build_comparison(ROOT)
        evidence = []
        for name, model in report["models"].items():
            test = model["calibrated_test"]["metrics"]
            external = model["external_calibrated_diagnostic"]["metrics"]
            evidence.append({"model": name, "hc3_test": {k: test[k] for k in ("human_fpr", "ai_recall", "coverage")},
                             "aide_diagnostic": {k: external[k] for k in ("human_fpr", "human_coverage")},
                             "blocked_model_gates": [g["id"] for g in model["calibrated_test"]["gates"] if g["status"] != "passed"]})
        print(json.dumps({"status": "blocked", "summary": "Two local detectors evaluated. Target-population, independence and unseen-generator evidence remain insufficient for product authorship claims.",
                          "evidence": evidence, "input_hashes": report["input_hashes"]}))
    except (OSError, KeyError, TypeError, ValueError) as error:
        print(json.dumps({"status": "failed", "summary": "Authorship experiment artifacts are missing, inconsistent or invalid.",
                          "evidence": [{"error": str(error)}]}))
        sys.exit(1)
