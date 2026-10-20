"""Lazy experimental hybrid service; no acquisition or user-text persistence."""
import math
import threading
import time

from .coaching import GPU_LOCK
from .research import ResearchBusy, ResearchUnavailable


def load_detector():
    from detector_models.hybrid import HybridDetector
    return HybridDetector(device='cpu')


class HybridResearch:
    def __init__(self, factory=None):
        self.factory = factory or load_detector
        self.model = None
        self.lock = threading.Lock()

    def analyze(self, text):
        if not self.lock.acquire(blocking=False):
            raise ResearchBusy('A hybrid comparison is still running.')
        if not GPU_LOCK.acquire(blocking=False):
            self.lock.release()
            raise ResearchBusy('Another local model is busy. Retry after it finishes.')
        started = time.perf_counter()
        try:
            if self.model is None:
                try:
                    self.model = self.factory()
                except Exception:
                    raise ResearchUnavailable('Hybrid models could not load. Run scripts/setup-hybrid.ps1 to install dependencies and pinned weights, then restart the app.') from None
            try:
                prediction = self.model.predict([{'id': 'web-hybrid', 'text': text}], batch_size=1)[0]
                score = prediction['score_ai']
                if type(score) not in (int, float) or not math.isfinite(score) or not 0 <= score <= 1:
                    raise ValueError('Invalid score.')
                result = {k: prediction[k] for k in ('model_id', 'model_revision', 'score_kind', 'score_ai',
                    'components', 'score_spread', 'disagreement', 'disagreement_threshold', 'coverage_complete')}
            except Exception:
                raise ResearchUnavailable('Hybrid inference could not finish. Try a shorter passage or restart the app.') from None
            result.update(status='experimental', product_approved=False, calibrated=False,
                elapsed_ms=round((time.perf_counter() - started) * 1000),
                limitations=[
                    'The equal-weight mean is an experimental index, not a probability or percentage of AI-written text.',
                    'DistilBERT and ModernBERT share training data. Agreement does not establish independent evidence or authorship.',
                    'Score spread of at least 0.25 flags disagreement; this threshold has not been validated for authorship decisions.',
                    'Each model has its own context limit. A truncated component scores only a prefix of the passage.',
                    'Detection accuracy and improvement over individual models have not been established for this hybrid.'
                ])
            return result
        finally:
            GPU_LOCK.release()
            self.lock.release()
