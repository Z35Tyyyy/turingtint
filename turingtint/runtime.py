"""Process-local admission and observable activity for one model request at a time."""
from __future__ import annotations

from contextlib import contextmanager
import threading
import time
from typing import Callable


class ModelBusy(Exception):
    """Another request still owns the model slot."""


class ModelActivity:
    def __init__(self, external_busy: Callable[[], bool]):
        self._mutex = threading.Lock()
        self._external_busy = external_busy
        self._task = None
        self._started = None

    def snapshot(self) -> dict:
        with self._mutex:
            busy = self._task is not None or self._external_busy()
            return {
                "busy": busy,
                "task": self._task or ("model" if busy else None),
                "elapsed_seconds": round(time.monotonic() - self._started, 1) if self._started is not None else None,
            }

    @contextmanager
    def claim(self, task: str):
        with self._mutex:
            if self._task is not None or self._external_busy():
                raise ModelBusy("A model task is still running. Controls will become available when it finishes.")
            self._task = task
            self._started = time.monotonic()
        try:
            # This spans the entire synchronous request, including loading and
            # all detector windows, even if the browser stops waiting for it.
            yield
        finally:
            with self._mutex:
                self._task = None
                self._started = None
