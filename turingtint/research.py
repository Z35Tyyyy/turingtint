"""Opt-in local detector experiments, separate from validated authorship claims."""
from __future__ import annotations

import math
import threading
import time

from .coaching import GPU_LOCK


class ResearchBusy(Exception):
    pass


class ResearchUnavailable(Exception):
    pass


def load_local_detector():
    # Import and load only after an explicit research request. MageDetector
    # verifies the pinned artifacts and uses local_files_only=True throughout.
    from detector_models.mage import MageDetector
    return MageDetector(device="auto", max_tokens=512)


class ResearchDetector:
    def __init__(self, factory=None):
        self._factory = factory or load_local_detector
        self._model = None
        self._lock = threading.Lock()

    def analyze(self, text: str) -> dict:
        if not self._lock.acquire(blocking=False):
            raise ResearchBusy("An experimental detector test is already running. Please retry shortly.")
        if not GPU_LOCK.acquire(blocking=False):
            self._lock.release()
            raise ResearchBusy("The local writing model is busy. Please retry after its review finishes.")
        started = time.perf_counter()
        try:
            if self._model is None:
                try:
                    self._model = self._factory()
                except Exception:
                    # Do not echo loader errors, filesystem paths or submitted text.
                    raise ResearchUnavailable("The local experimental model could not be loaded. Its verified model files and research dependencies must be installed.") from None
            try:
                prediction = self._model.predict([{"id": "web-research", "text": text}], batch_size=1)[0]
                score = prediction["score_ai"]
                if isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(score) or not 0 <= score <= 1:
                    raise ValueError("Invalid model output")
                result = {key: prediction[key] for key in (
                    "model_id", "model_revision", "score_kind", "original_tokens", "input_tokens", "max_tokens", "truncated", "device")}
            except Exception:
                raise ResearchUnavailable("The local experimental test could not finish. Try a shorter paragraph or restart the local app.") from None
            words = len(text.split())
            limitations = [
                "This uncalibrated score is not the probability or percentage of AI-written text.",
                "The model has not met this project's accuracy requirements for student writing.",
                "This test does not identify human, AI or mixed spans, and does not assess plagiarism.",
            ]
            if words < 80 or words > 250:
                limitations.append("The diagnostic experiments used 80-250-word excerpts; this passage is outside that range.")
            if prediction["truncated"]:
                limitations.append("Only the beginning fitted within the model's 512-token limit. The score does not cover the entire submitted passage.")
            result.update(status="experimental", product_approved=False, calibrated=False, score_ai=score,
                          input_characters=len(text), input_words=words,
                          elapsed_ms=round((time.perf_counter() - started) * 1000), limitations=limitations)
            return result
        finally:
            GPU_LOCK.release()
            self._lock.release()
