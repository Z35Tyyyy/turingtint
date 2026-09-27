"""Recompute the experimental decision policy's receipt without changing it."""
from pathlib import Path
import json
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from detector_eval.candidate import load_dataset, run, select_on_calibration


def check():
    source = ROOT / "evaluation/results/candidate-diagnostic.json"
    saved = json.loads(source.read_text(encoding="utf-8"))
    reference = json.loads((ROOT / "evaluation/results/phase2-comparison.json").read_text(encoding="utf-8"))
    rows, predictions = load_dataset(ROOT, "hc3", reference)
    selection, _ = select_on_calibration([r for r in rows if r["split"] == "calibration"], predictions)
    if saved["selection"] != selection or saved["product_approved"] is not False:
        raise ValueError("Calibration selection or experimental scope changed")
    with tempfile.TemporaryDirectory(prefix="turingtint-candidate-") as directory:
        copy = Path(directory) / "receipt.json"
        shutil.copyfile(source, copy)
        actual = run(ROOT, copy, "diagnose")
    for field in ("selection", "diagnostics", "score_recipe", "input_hashes", "product_approved", "phase"):
        if saved[field] != actual[field]:
            raise ValueError("Candidate diagnostic receipt differs from recomputation")
    evidence = []
    for name in ("hc3_test_retrospective", "aide_external_retrospective"):
        result = actual["diagnostics"][name]["frozen_primary_mage_candidate"]
        evidence.append({"dataset": name, **{key: result[key] for key in ("confusion", "coverage", "human_fpr", "ai_recall")}})
    return {"status": "passed", "summary": "Calibration choice and retrospective margin-policy metrics reproduce exactly; this checks evidence integrity, not authorship accuracy.", "evidence": evidence}


if __name__ == "__main__":
    try:
        print(json.dumps(check()))
    except (OSError, KeyError, TypeError, ValueError):
        print(json.dumps({"status": "failed", "summary": "Candidate policy evidence is missing, inconsistent or invalid."}))
        sys.exit(1)
