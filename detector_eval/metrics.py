"""Conservative, standard-library metrics for binary paragraph AI scores.

Records are mappings with id, label (0=human, 1=AI), score in [0,1], and an
optional source_group. Optional text_sha256 detects contradictory labels and
duplicate text; length_bucket, prompt, and generator produce subgroup reports.
Source groups are asserted document families, not proof of independent authors
or absence from detector pretraining. Those limitations survive a good score.

Threshold selection is restricted to a declared calibration split. Its error
caps are empirical calibration constraints, not confidence guarantees after
adaptive threshold selection. Product gates use separate test evidence and
Wilson bounds on human source-family events, counting any false AI flag in a
family as a failure. Repeated variants therefore cannot inflate the sample size.

Wilson bounds use z=NormalDist().inv_cdf(.95): lower and upper are each one-sided
95% bounds, not a joint two-sided 95% interval. Formula reference:
https://www.itl.nist.gov/div898/software/dataplot/refman2/auxillar/agrecoul.htm
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from bisect import bisect_left, bisect_right
from dataclasses import asdict, dataclass, fields
from statistics import NormalDist
from typing import Any, Iterable, Mapping, Sequence

SUBGROUP_FIELDS = ("length_bucket", "prompt", "generator")
SHA256 = re.compile(r"^[a-fA-F0-9]{64}$")


def _probability(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError(f"{name} must be a finite number between zero and one.")
    return float(value)


def _identifier(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a nonempty string.")
    return value


def _integer(value: Any, name: str, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}.")
    return value


def _ratio(numerator: int | float, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


@dataclass(frozen=True)
class FrozenThresholds:
    """Inclusive human/AI boundaries; the open interval means uncertain.

None disables that prediction class. Predefined thresholds support exploratory
metrics but cannot satisfy the calibration-provenance product gate.
"""

    human_max: float | None
    ai_min: float | None
    selected_on: str = "predefined"
    calibration_record_ids: tuple[str, ...] = ()
    calibration_group_ids: tuple[str, ...] = ()
    calibration_text_sha256: tuple[str, ...] = ()
    calibration_prompts: tuple[str, ...] = ()
    calibration_generators: tuple[str, ...] = ()
    calibration_sha256: str | None = None
    calibration_human_rows: int = 0
    calibration_ai_rows: int = 0
    ai_false_positive_cap: float = 0.01
    human_false_positive_cap: float = 0.01
    selection_method: str = "predefined"

    def __post_init__(self):
        for name in ("human_max", "ai_min"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, _probability(value, name))
        if self.human_max is not None and self.ai_min is not None and self.human_max >= self.ai_min:
            raise ValueError("human_max must be strictly lower than ai_min.")
        if self.selected_on not in {"predefined", "calibration"}:
            raise ValueError("Thresholds must be predefined or selected on calibration, never test.")
        for name in ("calibration_record_ids", "calibration_group_ids", "calibration_text_sha256", "calibration_prompts", "calibration_generators"):
            values = getattr(self, name)
            if not isinstance(values, (tuple, list)) or any(not isinstance(value, str) or not value for value in values):
                raise ValueError(f"{name} must contain nonempty strings.")
            object.__setattr__(self, name, tuple(sorted(set(values))))
        if self.calibration_sha256 is not None and not SHA256.fullmatch(self.calibration_sha256):
            raise ValueError("calibration_sha256 must be a SHA-256 hex digest.")
        for name in ("calibration_human_rows", "calibration_ai_rows"):
            _integer(getattr(self, name), name)
        for name in ("ai_false_positive_cap", "human_false_positive_cap"):
            _probability(getattr(self, name), name)

    def predict(self, score: float) -> str:
        score = _probability(score, "score")
        if self.ai_min is not None and score >= self.ai_min:
            return "ai"
        if self.human_max is not None and score <= self.human_max:
            return "human"
        return "uncertain"

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        for key, value in result.items():
            if isinstance(value, tuple):
                result[key] = list(value)
        return result

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "FrozenThresholds":
        if not isinstance(value, Mapping) or set(value) - {field.name for field in fields(cls)}:
            raise ValueError("Unknown frozen-threshold fields.")
        try:
            return cls(**value)
        except TypeError as exc:
            raise ValueError("Frozen thresholds require human_max and ai_min.") from exc


def _records(records: Iterable[Mapping[str, Any]], *, split: str | None = None) -> list[dict[str, Any]]:
    normalized = []
    seen_ids = set()
    hash_labels: dict[str, int] = {}
    for raw in records:
        if not isinstance(raw, Mapping):
            raise ValueError("Each score record must be a mapping.")
        record_id = _identifier(raw.get("id"), "record.id")
        if record_id in seen_ids:
            raise ValueError(f"Duplicate record id: {record_id}")
        seen_ids.add(record_id)
        label = raw.get("label")
        if isinstance(label, bool) or not isinstance(label, int) or label not in {0, 1}:
            raise ValueError("Labels must be integer 0 (human) or 1 (AI).")
        group = raw.get("source_group")
        if group is not None:
            _identifier(group, "source_group")
        if split is not None and raw.get("split", split) != split:
            raise ValueError(f"A record belongs to a different split than {split}.")
        record = {"id": record_id, "label": label, "score": _probability(raw.get("score"), "score"), "source_group": group}
        text_hash = raw.get("text_sha256")
        if text_hash is not None:
            if not isinstance(text_hash, str) or not SHA256.fullmatch(text_hash):
                raise ValueError("text_sha256 must be a SHA-256 hex digest.")
            text_hash = text_hash.lower()
            if text_hash in hash_labels and hash_labels[text_hash] != label:
                raise ValueError("Identical text has conflicting human/AI labels.")
            hash_labels[text_hash] = label
            record["text_sha256"] = text_hash
        for field in SUBGROUP_FIELDS:
            value = raw.get(field)
            if value is not None:
                if isinstance(value, bool) or not isinstance(value, (str, int)) or not str(value).strip():
                    raise ValueError(f"{field} must be a nonempty string or integer.")
                record[field] = str(value)
        normalized.append(record)
    return normalized


def _family_units(records: Sequence[dict[str, Any]]) -> dict[str, str]:
    """Merge declared families and exact-text duplicates, including cross-label families."""
    parent = {record["id"]: record["id"] for record in records}

    def find(value: str) -> str:
        while parent[value] != value:
            parent[value] = parent[parent[value]]
            value = parent[value]
        return value

    owners: dict[tuple[str, str], str] = {}
    for record in records:
        for field in ("source_group", "text_sha256"):
            value = record.get(field)
            if value is not None:
                key = (field, value)
                if key in owners:
                    parent[find(record["id"])] = find(owners[key])
                else:
                    owners[key] = record["id"]
    return {record["id"]: find(record["id"]) for record in records}


def wilson_one_sided_bounds(successes: int, total: int, *, confidence: float = 0.95) -> dict[str, Any]:
    """Return two separately one-sided Wilson bounds, null when total is zero."""
    _integer(successes, "successes")
    _integer(total, "total")
    if successes > total:
        raise ValueError("successes cannot exceed total.")
    confidence = _probability(confidence, "confidence")
    if not 0.5 < confidence < 1:
        raise ValueError("One-sided confidence must be strictly between .5 and 1.")
    result = {"method": "wilson_one_sided", "confidence": confidence, "successes": successes, "total": total, "lower": None, "upper": None}
    if total:
        z = NormalDist().inv_cdf(confidence)
        proportion = successes / total
        denominator = 1 + z * z / total
        center = (proportion + z * z / (2 * total)) / denominator
        half_width = z * math.sqrt(proportion * (1 - proportion) / total + z * z / (4 * total * total)) / denominator
        result.update(lower=max(0.0, center - half_width), upper=min(1.0, center + half_width))
    return result


def auroc(labels: Sequence[int], scores: Sequence[float]) -> float | None:
    """Mann–Whitney pair probability; ties receive half credit."""
    if len(labels) != len(scores):
        raise ValueError("Labels and scores must have equal length.")
    pairs = []
    for label, score in zip(labels, scores):
        if isinstance(label, bool) or not isinstance(label, int) or label not in {0, 1}:
            raise ValueError("Labels must be integer 0 or 1.")
        pairs.append((_probability(score, "score"), label))
    positive = sum(labels)
    negative = len(labels) - positive
    if not positive or not negative:
        return None
    pairs.sort()
    favorable = 0.0
    negative_seen = 0
    index = 0
    while index < len(pairs):
        end = index
        positives_here = negatives_here = 0
        while end < len(pairs) and pairs[end][0] == pairs[index][0]:
            positives_here += pairs[end][1]
            negatives_here += 1 - pairs[end][1]
            end += 1
        favorable += positives_here * negative_seen + 0.5 * positives_here * negatives_here
        negative_seen += negatives_here
        index = end
    return favorable / (positive * negative)


def select_thresholds(calibration_records: Iterable[Mapping[str, Any]], *, split: str = "calibration", ai_false_positive_cap: float = 0.01, human_false_positive_cap: float = 0.01) -> FrozenThresholds:
    """Freeze boundaries using calibration only; never accepts a test split.

AI threshold maximizes correctly detected AI families under the human-family
false-positive cap; ties minimize false flags then choose the higher boundary.
The human threshold then maximizes correct human families under the AI-family
false-human cap, remaining below the AI threshold. A side with no useful
admissible threshold is disabled. Caps are empirical, not confidence claims.
"""
    if split != "calibration":
        raise ValueError("Threshold selection is allowed only on calibration data.")
    ai_false_positive_cap = _probability(ai_false_positive_cap, "ai_false_positive_cap")
    human_false_positive_cap = _probability(human_false_positive_cap, "human_false_positive_cap")
    records = _records(calibration_records, split=split)
    human = [record for record in records if record["label"] == 0]
    ai = [record for record in records if record["label"] == 1]
    if not human or not ai:
        raise ValueError("Calibration needs both human and AI examples.")
    units = _family_units(records)
    human_units = {units[record["id"]] for record in human}
    ai_units = {units[record["id"]] for record in ai}
    candidates = sorted({record["score"] for record in records})
    maximums: dict[int, dict[str, float]] = {0: {}, 1: {}}
    minimums: dict[int, dict[str, float]] = {0: {}, 1: {}}
    for record in records:
        unit = units[record["id"]]
        label = record["label"]
        maximums[label][unit] = max(maximums[label].get(unit, 0.0), record["score"])
        minimums[label][unit] = min(minimums[label].get(unit, 1.0), record["score"])
    high_human, high_ai = sorted(maximums[0].values()), sorted(maximums[1].values())
    low_human, low_ai = sorted(minimums[0].values()), sorted(minimums[1].values())
    ai_options = []
    for candidate in candidates:
        false_count = len(high_human) - bisect_left(high_human, candidate)
        true_count = len(high_ai) - bisect_left(high_ai, candidate)
        if true_count and false_count / len(human_units) <= ai_false_positive_cap:
            ai_options.append((true_count, -false_count, candidate))
    ai_min = max(ai_options)[2] if ai_options else None
    human_options = []
    for candidate in candidates:
        if ai_min is not None and candidate >= ai_min:
            continue
        false_count = bisect_right(low_ai, candidate)
        true_count = bisect_right(low_human, candidate)
        if true_count and false_count / len(ai_units) <= human_false_positive_cap:
            human_options.append((true_count, -false_count, -candidate))
    human_max = -max(human_options)[2] if human_options else None
    serialized = json.dumps(sorted(records, key=lambda record: record["id"]), sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return FrozenThresholds(
        human_max=human_max, ai_min=ai_min, selected_on="calibration",
        calibration_record_ids=tuple(record["id"] for record in records),
        calibration_group_ids=tuple(record["source_group"] for record in records if record["source_group"] is not None),
        calibration_text_sha256=tuple(record["text_sha256"] for record in records if record.get("text_sha256")),
        calibration_prompts=tuple(record["prompt"] for record in records if record.get("prompt")),
        calibration_generators=tuple(record["generator"] for record in ai if record.get("generator")),
        calibration_sha256=hashlib.sha256(serialized).hexdigest(),
        calibration_human_rows=len(human), calibration_ai_rows=len(ai),
        ai_false_positive_cap=ai_false_positive_cap, human_false_positive_cap=human_false_positive_cap,
        selection_method="empirical_source_family_error_caps_on_calibration_only",
    )


def _summarize(records: Sequence[dict[str, Any]], thresholds: FrozenThresholds) -> dict[str, Any]:
    confusion = {name: 0 for name in ("tp", "fp", "tn", "fn", "abstain_human", "abstain_ai")}
    predictions = {}
    for record in records:
        prediction = thresholds.predict(record["score"])
        predictions[record["id"]] = prediction
        if prediction == "uncertain":
            confusion["abstain_ai" if record["label"] else "abstain_human"] += 1
        elif prediction == "ai":
            confusion["tp" if record["label"] else "fp"] += 1
        else:
            confusion["fn" if record["label"] else "tn"] += 1
    human = [record for record in records if record["label"] == 0]
    ai = [record for record in records if record["label"] == 1]
    units = _family_units(records)
    human_groups = {units[record["id"]] for record in human if record["source_group"] is not None}
    ai_groups = {units[record["id"]] for record in ai if record["source_group"] is not None}
    false_groups = {units[record["id"]] for record in human if record["source_group"] is not None and predictions[record["id"]] == "ai"}
    ai_missed_groups = {units[record["id"]] for record in ai if record["source_group"] is not None and predictions[record["id"]] != "ai"}
    missing_groups = sum(record["source_group"] is None for record in records)
    human_groups_complete = all(record["source_group"] is not None for record in human)
    group_bounds = wilson_one_sided_bounds(len(false_groups), len(human_groups)) if human_groups_complete else None
    answered_human = confusion["fp"] + confusion["tn"]
    answered_ai = confusion["tp"] + confusion["fn"]
    return {
        "counts": {"records": len(records), "human": len(human), "ai": len(ai), "human_source_groups": len(human_groups), "ai_source_groups": len(ai_groups), "missing_source_groups": missing_groups},
        "confusion": confusion,
        "human_fpr": _ratio(confusion["fp"], len(human)),
        "answered_human_fpr": _ratio(confusion["fp"], answered_human),
        "false_human_rate": _ratio(confusion["fn"], len(ai)),
        "ai_recall": _ratio(confusion["tp"], len(ai)),
        "human_recall": _ratio(confusion["tn"], len(human)),
        "ai_precision": _ratio(confusion["tp"], confusion["tp"] + confusion["fp"]),
        "human_precision": _ratio(confusion["tn"], confusion["tn"] + confusion["fn"]),
        "coverage": _ratio(answered_human + answered_ai, len(records)),
        "human_coverage": _ratio(answered_human, len(human)),
        "ai_coverage": _ratio(answered_ai, len(ai)),
        "ai_group_recall": _ratio(len(ai_groups - ai_missed_groups), len(ai_groups)),
        "brier": _ratio(sum((record["score"] - record["label"]) ** 2 for record in records), len(records)),
        "auroc": auroc([record["label"] for record in records], [record["score"] for record in records]),
        "human_group_fpr": {"event": "at_least_one_false_ai_flag_per_human_source_family", "false_positive_groups": len(false_groups), "human_groups": len(human_groups), "estimate": _ratio(len(false_groups), len(human_groups)), "bounds": group_bounds, "independence_is_assumed_not_inferred": True},
    }


def evaluate(records: Iterable[Mapping[str, Any]], thresholds: FrozenThresholds, *, split: str = "test", unseen_generator_evidence: bool = False, independent_source_groups_verified: bool = False, require_prompt_disjoint: bool = False, min_human_groups: int = 300, min_ai_groups: int = 100) -> dict[str, Any]:
    """Apply frozen thresholds, report metrics, and keep unsupported release blocked.

The caller must supply genuine external independence/unseen-generator evidence;
booleans are attributed assertions, not proof. Product approval covers configured
binary paragraph claims only, never sentences, mixed authorship, or all models.
"""
    if not isinstance(thresholds, FrozenThresholds):
        raise ValueError("Use a FrozenThresholds object; do not tune during evaluation.")
    if split not in {"test", "calibration", "development"}:
        raise ValueError("Evaluation split must be test, calibration, or development.")
    for value in (unseen_generator_evidence, independent_source_groups_verified, require_prompt_disjoint):
        if not isinstance(value, bool):
            raise ValueError("Evidence and prompt-disjointness flags must be booleans.")
    _integer(min_human_groups, "min_human_groups", 300)
    _integer(min_ai_groups, "min_ai_groups", 100)
    normalized = _records(records, split=split)
    if split == "test":
        if {record["id"] for record in normalized} & set(thresholds.calibration_record_ids):
            raise ValueError("Calibration/test record overlap; test data cannot select thresholds.")
        if {record["source_group"] for record in normalized if record["source_group"] is not None} & set(thresholds.calibration_group_ids):
            raise ValueError("Calibration/test source-family overlap.")
        if {record["text_sha256"] for record in normalized if record.get("text_sha256")} & set(thresholds.calibration_text_sha256):
            raise ValueError("Calibration/test exact-text overlap.")
        if require_prompt_disjoint:
            if any(not record.get("prompt") for record in normalized) or not thresholds.calibration_prompts:
                raise ValueError("Prompt-disjoint evaluation requires known calibration and test prompts.")
            if {record["prompt"] for record in normalized} & set(thresholds.calibration_prompts):
                raise ValueError("Calibration/test prompts overlap.")
    metrics = _summarize(normalized, thresholds)
    subgroups: dict[str, Any] = {}
    for field in SUBGROUP_FIELDS:
        values = sorted({record[field] for record in normalized if record.get(field) is not None})
        if values:
            subgroups[field] = {value: _summarize([record for record in normalized if record.get(field) == value], thresholds) for value in values}
            missing = [record for record in normalized if record.get(field) is None]
            if missing:
                missing_key = "__missing__"
                while missing_key in subgroups[field]:
                    missing_key = "_" + missing_key
                subgroups[field][missing_key] = _summarize(missing, thresholds)
    group_bounds = metrics["human_group_fpr"]["bounds"]
    upper_fpr = group_bounds["upper"] if group_bounds else None
    test_generators = {record["generator"] for record in normalized if record["label"] == 1 and record.get("generator")}
    unseen_generators = sorted(test_generators - set(thresholds.calibration_generators))
    unseen_generator_validation = {}
    for generator in unseen_generators:
        generator_metrics = _summarize([record for record in normalized if record["label"] == 1 and record.get("generator") == generator], thresholds)
        enough_groups = generator_metrics["counts"]["ai_source_groups"] >= min_ai_groups and generator_metrics["counts"]["missing_source_groups"] == 0
        good_recall = generator_metrics["ai_recall"] is not None and generator_metrics["ai_recall"] >= .8 and generator_metrics["ai_group_recall"] is not None and generator_metrics["ai_group_recall"] >= .8
        unseen_generator_validation[generator] = {"metrics": generator_metrics, "minimum_ai_groups": min_ai_groups, "status": "passed" if enough_groups and good_recall else "blocked"}
    unseen_evidence_passed = bool(unseen_generator_evidence and thresholds.calibration_generators and unseen_generator_validation and all(result["status"] == "passed" for result in unseen_generator_validation.values()) and all(record.get("generator") for record in normalized if record["label"] == 1))
    calibration_verified = bool(thresholds.selected_on == "calibration" and thresholds.calibration_sha256 and thresholds.calibration_record_ids and thresholds.calibration_human_rows > 0 and thresholds.calibration_ai_rows > 0)
    independence_complete = metrics["counts"]["missing_source_groups"] == 0 and independent_source_groups_verified
    checks = [
        ("test_split", split == "test", "Release evidence must come from a test split."),
        ("calibration_provenance", calibration_verified, "Thresholds must be frozen on separately declared calibration data."),
        ("independent_source_groups", independence_complete, "Known source-family identifiers and external independence evidence are required."),
        ("minimum_human_groups", metrics["counts"]["human_source_groups"] >= min_human_groups, f"At least {min_human_groups} distinct human source families are required."),
        ("minimum_ai_groups", metrics["counts"]["ai_source_groups"] >= min_ai_groups, f"At least {min_ai_groups} distinct pure-AI source families are required."),
        ("human_fpr_upper_95", upper_fpr is not None and upper_fpr <= .01 and metrics["human_fpr"] is not None and metrics["human_fpr"] <= .01, "Human-row FPR and the one-sided 95% Wilson upper human-family false-AI rate must each be <= 1%."),
        ("ai_recall", metrics["ai_recall"] is not None and metrics["ai_recall"] >= .8 and metrics["ai_group_recall"] is not None and metrics["ai_group_recall"] >= .8, "AI row recall and all-variants-correct family recall must be >= 80%, counting abstentions as misses."),
        ("coverage", metrics["coverage"] is not None and metrics["coverage"] >= .6, "Conclusive paragraph coverage must be >= 60%."),
        ("unseen_generator_evidence", unseen_evidence_passed, f"Each identified unseen generator requires >= {min_ai_groups} known AI source families and >= 80% row and all-variants-correct family recall, plus external evidence and complete generator metadata."),
    ]
    gates = [{"id": name, "status": "passed" if passed else "blocked", "reason": reason} for name, passed, reason in checks]
    return {
        "version": 1, "scope": "binary paragraph scores; uncertainty is not mixed authorship",
        "split": split, "thresholds": thresholds.to_dict(), "metrics": metrics, "subgroups": subgroups,
        "gates": gates, "product_approved": all(passed for _, passed, _ in checks),
        "insufficient_independence": not independence_complete,
        "unseen_test_generators": unseen_generators,
        "unseen_generator_validation": unseen_generator_validation,
        "limitations": ["No sentence or mixed-authorship accuracy claim.", "Public-data provenance does not establish absence from model pretraining.", "Source-family IDs and evidence flags are supplied assertions, not inferred proof of independent authors.", "Subgroup metrics and Wilson bounds are descriptive; no simultaneous subgroup guarantee is claimed.", "Aggregate gates do not establish generalization to unsupported populations or generators."],
    }
