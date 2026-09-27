"""Bounded local model opinions with explicit context and coverage limits.

These provisional thresholds were selected on an out-of-domain research corpus.
Agreement is an experimental model opinion, not validated authorship evidence.
Context blocks are not sentence-level localization or a mixed-authorship class.
"""

from __future__ import annotations

from contextlib import nullcontext
import hashlib
import io
import json
import math
from numbers import Real
from pathlib import Path
import re
import threading
import time
from typing import Any

from .research import ResearchBusy, ResearchDetector, ResearchUnavailable
from .text import utf16_offset

ROOT = Path(__file__).resolve().parents[1]
MIN_CONTEXT_WORDS = 80
MAX_CONTEXT_WORDS = 250
MAX_WINDOW_WORDS = 200
MAX_INPUT_CHARACTERS = 50_000
MAX_MODEL_BYTES = 128 * 1024 * 1024
MODEL_NAMES = {"mage": "MAGE local language-model detector", "tfidf": "Local TF-IDF / logistic detector"}
RAW_KINDS = {"mage": "uncalibrated_softmax_class_0", "tfidf": "uncalibrated_logistic_class_1"}
LABELS = {"ai_leaning", "human_leaning", "inconclusive"}


def _sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Expected a local artifact receipt.")
    return value


def load_verified_baseline(root: Path = ROOT):
    """Load only the exact locally trained bytes named in the training receipt.

This authenticates consistency with a trusted local receipt, not a signature for
untrusted pickle files. The application accepts no user-supplied model path.
"""
    folder = root / "outputs/experiments/tfidf-v1"
    receipt = _json(folder / "report.json")["experiment"]
    path = folder / "baseline.joblib"
    if path.stat().st_size > MAX_MODEL_BYTES:
        raise ResearchUnavailable("The local baseline artifact exceeds its expected resource limit.")
    content = path.read_bytes()
    expected = receipt.get("model_sha256")
    if not isinstance(expected, str) or not re.fullmatch(r"[a-f0-9]{64}", expected) or _sha_bytes(content) != expected:
        raise ResearchUnavailable("The local baseline does not match its training receipt.")
    # Deserialize the same bytes that were hashed, avoiding a second path read.
    import joblib

    return joblib.load(io.BytesIO(content))


def _threshold_pair(value: Any) -> dict[str, float | None]:
    if not isinstance(value, dict) or not {"human_max", "ai_min"} <= value.keys():
        raise ValueError("Missing provisional thresholds.")
    result = {}
    for name in ("human_max", "ai_min"):
        number = value[name]
        if number is not None and (isinstance(number, bool) or not isinstance(number, (int, float)) or not math.isfinite(number) or not 0 <= number <= 1):
            raise ValueError("Invalid provisional thresholds.")
        result[name] = None if number is None else float(number)
    if result["human_max"] is not None and result["ai_min"] is not None and result["human_max"] >= result["ai_min"]:
        raise ValueError("Provisional thresholds overlap.")
    return result


def load_verified_thresholds(root: Path = ROOT) -> dict[str, dict[str, float | None]]:
    """Verify each model's research thresholds independently, without retraining.

Unavailable or inconsistent evidence disables that model's leaning labels.
Recompute only the declared calibration selection, never optimize on test data.
"""
    from detector_eval.experiment import attach_scores, load_frozen, read_jsonl
    from detector_eval.metrics import select_thresholds

    try:
        comparison = _json(root / "evaluation/results/phase2-comparison.json")
        frozen = root / "data/authorship/experiments/hc3-v1"
        rows, manifest = load_frozen(frozen)
        if manifest["records_sha256"] != comparison["input_hashes"]["hc3"]:
            return {}
        ids = {row["id"] for row in rows}
    except (OSError, ValueError, KeyError, TypeError):
        return {}
    verified = {}
    for model_id, comparison_id in (("tfidf", "tfidf_logistic"), ("mage", "mage_raw_text_512")):
        try:
            expected = comparison["models"][comparison_id]["calibrated_test"]["thresholds"]
            if expected["selected_on"] != "calibration":
                continue
            if model_id == "tfidf":
                folder = root / "outputs/experiments/tfidf-v1"
                original = _json(folder / "report.json")
                receipt = original["experiment"]
                predictions_path = folder / "predictions.jsonl"
                if (_sha_file(folder / "baseline.joblib") != receipt["model_sha256"]
                        or _sha_file(frozen / "manifest.json") != receipt["frozen_manifest_sha256"]
                        or _sha_file(predictions_path) != receipt["predictions_sha256"]
                        or receipt["predictions_sha256"] != comparison["input_hashes"]["tfidf_predictions"]):
                    continue
                predictions = [row for row in read_jsonl(predictions_path) if row["id"] in ids]
                scored = attach_scores(rows, predictions, hash_kind="normalized")
            else:
                from detector_models.mage import MODEL_ID, MODEL_REVISION, PREPROCESSING, verify_manifest

                model_dir = root / ".cache/detector-models/mage"
                if _sha_file(model_dir / "manifest.json") != comparison["input_hashes"]["mage_manifest"]:
                    continue
                model_manifest = verify_manifest(model_dir)
                if model_manifest.get("inference_allowed") is not True:
                    continue
                predictions_path = root / "outputs/experiments/mage-hc3-v1/predictions.jsonl"
                if _sha_file(predictions_path) != comparison["input_hashes"]["mage_hc3_predictions"]:
                    continue
                predictions = read_jsonl(predictions_path)
                if any(row.get("model_id") != MODEL_ID or row.get("model_revision") != MODEL_REVISION
                       or row.get("preprocessing") != PREPROCESSING or row.get("max_tokens") != 512
                       or row.get("score_kind") != RAW_KINDS["mage"] for row in predictions):
                    continue
                scored = attach_scores(rows, predictions)
            selected = select_thresholds([row for row in scored if row["split"] == "calibration"])
            actual = selected.to_dict()
            if any(actual[key] != expected[key] for key in ("human_max", "ai_min", "selected_on", "calibration_sha256")):
                continue
            verified[model_id] = _threshold_pair(expected)
        except (OSError, ValueError, KeyError, TypeError, RuntimeError, ImportError):
            continue
    return verified


def _blocks(text: str, target_words: int, maximum_windows: int) -> list[dict[str, Any]]:
    words = list(re.finditer(r"\S+", text))
    count = len(words)
    if count <= MAX_CONTEXT_WORDS:
        sizes = [count]
    elif count <= maximum_windows * MAX_WINDOW_WORDS:
        number = min(maximum_windows, math.ceil(count / target_words))
        base, remainder = divmod(count, number)
        sizes = [base + (index < remainder) for index in range(number)]
    else:
        sizes = [MAX_WINDOW_WORDS] * maximum_windows
    result = []
    word_index = start = 0
    for size in sizes:
        word_index += size
        end = words[word_index].start() if word_index < count else len(text)
        result.append({"start_py": start, "end_py": end, "text": text[start:end], "words": int(size), "scheduled": True})
        start = end
    if start < len(text):
        result.append({"start_py": start, "end_py": len(text), "text": text[start:], "words": count - word_index, "scheduled": False})
    return result


def _score(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError("A model score must be finite and between zero and one.")
    number = float(value)
    if not math.isfinite(number) or not 0 <= number <= 1:
        raise ValueError("A model score must be finite and between zero and one.")
    return number


def _lean(score: float, thresholds: dict[str, float | None] | None) -> str:
    if thresholds is None:
        return "inconclusive"
    if thresholds["ai_min"] is not None and score >= thresholds["ai_min"]:
        return "ai_leaning"
    if thresholds["human_max"] is not None and score <= thresholds["human_max"]:
        return "human_leaning"
    return "inconclusive"


def _opinion(model_id: str, *, status: str, score: float | None = None, label: str = "inconclusive", reason: str) -> dict[str, Any]:
    return {"id": model_id, "name": MODEL_NAMES[model_id], "status": status, "label": label,
            "score_ai": score, "score_kind": RAW_KINDS[model_id], "reason": reason}


class WorkbenchDetector:
    """Serial, bounded context scoring with trusted factories for test injection."""

    def __init__(self, research_detector=None, *, root: Path | str | None = None,
                 baseline_loader=None, threshold_loader=None, max_windows: int = 12, target_words: int = 180):
        if isinstance(max_windows, bool) or not isinstance(max_windows, int) or not 1 <= max_windows <= 12:
            raise ValueError("max_windows must be an integer between one and twelve.")
        if isinstance(target_words, bool) or not isinstance(target_words, int) or not 150 <= target_words <= MAX_WINDOW_WORDS:
            raise ValueError("target_words must be an integer between 150 and 200.")
        self.root = Path(root).resolve() if root is not None else ROOT
        self.research = research_detector if research_detector is not None else ResearchDetector()
        self._baseline_loader = baseline_loader or (lambda: load_verified_baseline(self.root))
        self._threshold_loader = threshold_loader or (lambda: load_verified_thresholds(self.root))
        self._baseline = None
        self._thresholds = None
        self._lock = threading.Lock()
        self.max_windows = max_windows
        self.target_words = target_words

    def _load(self) -> tuple[dict[str, dict], bool]:
        if self._thresholds is None:
            try:
                loaded = self._threshold_loader()
                if not isinstance(loaded, dict):
                    raise ValueError("Invalid threshold provider.")
                self._thresholds = {}
                for name in MODEL_NAMES:
                    if name in loaded:
                        try:
                            self._thresholds[name] = _threshold_pair(loaded[name])
                        except (ValueError, TypeError):
                            pass
            except Exception:
                self._thresholds = {}
        if self._baseline is None:
            try:
                self._baseline = self._baseline_loader()
                classes = list(self._baseline.classes_)
                if len(classes) != 2 or set(classes) != {0, 1} or any(isinstance(value, bool) for value in classes):
                    raise ValueError("Unexpected baseline label mapping.")
            except Exception:
                self._baseline = None
        return self._thresholds, self._baseline is not None

    def _model_opinions(self, block: dict[str, Any], thresholds: dict[str, dict], baseline_available: bool) -> list[dict[str, Any]]:
        opinions = []
        supported_length = MIN_CONTEXT_WORDS <= block["words"] <= MAX_CONTEXT_WORDS
        for model_id in ("mage", "tfidf"):
            if not block["scheduled"]:
                opinions.append(_opinion(model_id, status="not_scored", reason="Outside the bounded context-window budget; this text was not scored."))
                continue
            try:
                if model_id == "mage":
                    prediction = self.research.analyze(block["text"])
                    value = _score(prediction["score_ai"])
                    if prediction.get("input_characters") != len(block["text"]):
                        raise ValueError("Model did not report the complete submitted context.")
                    if prediction.get("score_kind") != RAW_KINDS[model_id] or not isinstance(prediction.get("truncated"), bool):
                        raise ValueError("Invalid research-model metadata.")
                    original_tokens, input_tokens = prediction.get("original_tokens"), prediction.get("input_tokens")
                    if (prediction.get("max_tokens") != 512 or isinstance(original_tokens, bool) or isinstance(input_tokens, bool)
                            or not isinstance(original_tokens, int) or not isinstance(input_tokens, int)
                            or not 0 < input_tokens <= original_tokens or input_tokens > 512):
                        raise ValueError("Invalid token coverage metadata.")
                    if prediction["truncated"] or input_tokens < original_tokens:
                        opinion = _opinion(model_id, status="truncated", score=value, reason="Only the beginning of this context fitted the model token limit; no whole-block leaning is assigned.")
                        opinion.update(original_tokens=prediction.get("original_tokens"), input_tokens=prediction.get("input_tokens"), max_tokens=prediction.get("max_tokens"))
                        opinions.append(opinion)
                        continue
                else:
                    if not baseline_available:
                        raise ResearchUnavailable("The verified local baseline is unavailable.")
                    position = list(self._baseline.classes_).index(1)
                    # Thread limits apply only if the optional ML dependencies are
                    # installed; injected standard-library test doubles need none.
                    try:
                        from threadpoolctl import threadpool_limits
                        limit = threadpool_limits(limits=2)
                    except ImportError:
                        limit = nullcontext()
                    with limit:
                        probabilities = self._baseline.predict_proba([block["text"]])
                    value = _score(probabilities[0][position])
                label = _lean(value, thresholds.get(model_id)) if supported_length else "inconclusive"
                if not supported_length:
                    reason = "This context is shorter than the 80-word research range; its raw score is shown without a leaning label."
                elif model_id not in thresholds:
                    reason = "The raw model score is available, but its provisional research thresholds could not be verified."
                elif label == "inconclusive":
                    reason = "This raw score lies between the model's provisional human-leaning and AI-leaning boundaries."
                else:
                    reason = "This context crosses a provisional research boundary; this is an unvalidated model opinion, not proof of authorship."
                opinions.append(_opinion(model_id, status="ok", score=value, label=label, reason=reason))
            except ResearchBusy:
                raise
            except Exception:
                opinions.append(_opinion(model_id, status="unavailable", reason="This verified local model could not score the context; no authorship conclusion is assigned."))
        return opinions

    @staticmethod
    def _combine(opinions: list[dict[str, Any]], words: int, scheduled: bool) -> tuple[str, str]:
        if not scheduled:
            return "inconclusive", "The window limit was reached; this remaining text was not scored."
        if words < MIN_CONTEXT_WORDS:
            return "inconclusive", "This short context is outside the research length range; model scores cannot support a leaning label."
        if any(opinion["status"] != "ok" for opinion in opinions):
            return "inconclusive", "Both models must process the entire context before a combined leaning is assigned."
        labels = {opinion["label"] for opinion in opinions}
        if len(labels) == 1 and "inconclusive" not in labels:
            return labels.pop(), "Both models lean the same way for this context block. This is experimental block evidence, not validated sentence authorship."
        if labels == {"ai_leaning", "human_leaning"}:
            return "inconclusive", "The models disagree about this context. Disagreement does not establish mixed human/AI authorship."
        return "inconclusive", "At least one model has no supported leaning for this context; the combined result remains uncertain."

    @staticmethod
    def _aggregate(model_id: str, segments: list[dict[str, Any]]) -> dict[str, Any]:
        opinions = [next(item for item in segment["models"] if item["id"] == model_id) for segment in segments]
        scored = [(opinion["score_ai"], segment["words"]) for opinion, segment in zip(opinions, segments) if opinion["score_ai"] is not None]
        labels = {opinion["label"] for opinion in opinions}
        complete = all(opinion["status"] == "ok" for opinion in opinions)
        label = next(iter(labels)) if complete and len(labels) == 1 else "inconclusive"
        if not scored:
            status = "unavailable"
            score = None
            reason = "No context scores are available from this model."
        else:
            status = "ok" if complete else "partial"
            score = sum(value * count for value, count in scored) / sum(count for _, count in scored)
            reason = "One raw context score." if len(scored) == 1 else "Word-weighted mean of available raw context scores; boundaries were applied separately to each block, never to this mean."
            if not complete:
                reason += " This model did not fully process every context."
            if label == "inconclusive":
                reason += " Context opinions do not support one consistent passage leaning."
        result = _opinion(model_id, status=status, score=score, label=label, reason=reason)
        if len(scored) > 1:
            result["score_kind"] = "word_weighted_mean_uncalibrated_context_scores"
        result["scored_contexts"] = len(scored)
        result["total_contexts"] = len(segments)
        return result

    def analyze(self, text: str) -> dict[str, Any]:
        if not isinstance(text, str) or not text.strip() or len(text) > MAX_INPUT_CHARACTERS:
            raise ValueError("Use nonempty text of at most 50,000 characters.")
        if "\x00" in text or any(0xD800 <= ord(character) <= 0xDFFF for character in text):
            raise ValueError("Text contains invalid characters.")
        if not self._lock.acquire(blocking=False):
            raise ResearchBusy("A local model assessment is already running. Please retry shortly.")
        started = time.perf_counter()
        try:
            thresholds, baseline_available = self._load()
            blocks = _blocks(text, self.target_words, self.max_windows)
            segments = []
            analyzed_characters = 0
            for block in blocks:
                opinions = self._model_opinions(block, thresholds, baseline_available)
                label, reason = self._combine(opinions, block["words"], block["scheduled"])
                complete = block["scheduled"] and all(opinion["status"] == "ok" for opinion in opinions)
                if complete:
                    analyzed_characters += len(block["text"])
                segments.append({"start": utf16_offset(text, block["start_py"]), "end": utf16_offset(text, block["end_py"]),
                                 "text": block["text"], "words": block["words"], "label": label, "reason": reason,
                                 "models": opinions, "coverage_complete": complete,
                                 "evidence_scope": "context_block_not_sentence_authorship"})
            full_coverage = analyzed_characters == len(text)
            labels = {segment["label"] for segment in segments}
            if full_coverage and len(labels) == 1 and "inconclusive" not in labels:
                label = next(iter(labels))
                direction = "AI-leaning" if label == "ai_leaning" else "human-leaning"
                summary = f"Both local models are provisionally {direction} across all scored context blocks. This experimental agreement does not prove how the passage was written."
            else:
                label = "inconclusive"
                summary = "The local models do not provide consistent, fully supported evidence for one passage-level leaning. Review the individual model opinions and context limits below."
            truncated = any(not block["scheduled"] for block in blocks) or any(opinion["status"] == "truncated" for segment in segments for opinion in segment["models"])
            limitations = [
                "These are experimental ML opinions using provisional thresholds from an out-of-domain research corpus; student-writing accuracy has not been established.",
                "Raw model scores and averages are not the probability or percentage of AI-written text.",
                "Highlighted blocks show contextual model evidence, not validated sentence or word authorship; disagreements are not mixed-authorship labels.",
                "Analyzed-character coverage counts only contexts fully processed by both models. A missing model, short context, uncertainty or changing block opinions prevents a combined conclusion.",
                "Agreement between these models does not establish independent evidence, provenance, or plagiarism.",
            ]
            if truncated:
                limitations.append("Some text was outside a window/token limit. Unscored or partially processed contexts remain inconclusive.")
            if any(block["words"] < MIN_CONTEXT_WORDS for block in blocks if block["scheduled"]):
                limitations.append("Contexts shorter than 80 words receive raw scores only; provisional leaning labels are withheld.")
            return {"status": "experimental", "product_approved": False, "validated": False,
                    "assessment": {"label": label, "summary": summary},
                    "models": [self._aggregate(name, segments) for name in ("mage", "tfidf")],
                    "segments": segments, "offset_encoding": "utf-16",
                    "input": {"characters": len(text), "words": len(text.split()), "analyzed_characters": analyzed_characters,
                              "truncated": truncated, "coverage_complete": full_coverage,
                              "scored_windows": sum(block["scheduled"] for block in blocks), "window_limit": self.max_windows},
                    "limitations": limitations, "elapsed_ms": round((time.perf_counter() - started) * 1000)}
        finally:
            self._lock.release()
