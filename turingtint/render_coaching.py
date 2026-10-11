"""Optional, explicitly selected cloud coach for the small Render CPU service."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import time

from .coaching import GPU_LOCK, LIMITATIONS, MAX_CHARS, messages, validate_output

DEFAULT_GROQ_MODEL = "qwen/qwen3.8-27b"
GROQ_ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"
CODE_SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


class GroqWritingCoach:
    """No model loading and no external request unless provider='groq'."""

    def __init__(self, *, http_client_factory=None):
        self._http_client_factory = http_client_factory

    @property
    def model(self):
        return os.getenv("TURINGTINT_GROQ_MODEL", "").strip() or DEFAULT_GROQ_MODEL

    def status(self):
        return {"default_provider": "none", "product_approved": False,
                "local": {"available": False, "model": None, "sends_text_off_device": False},
                "openai": {"available": False, "model": None, "sends_text_off_device": True},
                "groq": {"available": bool(os.getenv("GROQ_API_KEY", "").strip()),
                         "model": self.model, "sends_text_off_device": True}}

    def _request(self, text):
        import httpx
        key = os.getenv("GROQ_API_KEY", "").strip()
        if not key:
            raise ValueError("Provider unconfigured")
        payload = {"model": self.model, "messages": messages(text),
                   "max_completion_tokens": 1200, "temperature": 0,
                   "response_format": {"type": "json_object"}, "stream": False}
        if self.model.startswith("qwen/"):
            payload["reasoning_effort"] = "none"
        factory = self._http_client_factory or httpx.Client
        with factory(timeout=httpx.Timeout(45, connect=10), follow_redirects=False, trust_env=False) as client:
            with client.stream("POST", GROQ_ENDPOINT,
                               headers={"Authorization": "Bearer " + key}, json=payload) as response:
                response.raise_for_status()
                chunks = bytearray()
                deadline = time.monotonic() + 60
                for chunk in response.iter_bytes():
                    if time.monotonic() > deadline or len(chunks) + len(chunk) > 128000:
                        raise ValueError("Provider response limit")
                    chunks.extend(chunk)
        data = json.loads(chunks)
        choices = data["choices"]
        if not isinstance(choices, list) or len(choices) != 1:
            raise ValueError("Invalid choices")
        choice = choices[0]
        message = choice["message"]
        if choice.get("finish_reason") != "stop" or message.get("refusal") or message.get("tool_calls"):
            raise ValueError("Incomplete review")
        return message["content"]

    def review(self, text, provider="none"):
        started = time.perf_counter()
        base = {"provider": provider, "model": self.model if provider == "groq" else None,
                "product_approved": False, "coach_code_sha256": CODE_SHA256,
                "limitations": list(LIMITATIONS) + [
                    "This optional review sends the passage to Groq. Provider data policies apply."]}

        def unavailable(reason):
            return {**base, "status": "unavailable", "reason": reason,
                    "elapsed_ms": round((time.perf_counter() - started) * 1000)}

        if provider != "groq":
            return unavailable("Cloud coaching is off. Explicitly select Groq to request a review.")
        if not self.status()["groq"]["available"]:
            return unavailable("The optional Groq writing coach is not configured on this server.")
        if (not isinstance(text, str) or not text.strip() or len(text) > MAX_CHARS
                or any(ord(c) == 0 or 0xD800 <= ord(c) <= 0xDFFF for c in text)):
            return unavailable("Use a nonempty passage of at most 8,000 characters with valid Unicode.")
        if not GPU_LOCK.acquire(blocking=False):
            return unavailable("A model task is already running. Please retry shortly.")
        try:
            result = validate_output(self._request(text), text)
            if result.get("protected_numeric_suggestions"):
                base["limitations"].append("Suggestions for complete sentences containing digits were discarded by the conservative numeric-protection policy; numeric facts and units were not verified.")
            if result["discarded_suggestions"]:
                base["limitations"].append("Suggestions with invalid references, unchanged rewrites or serialized formatting artifacts were discarded.")
            if any(item.get("rewrite_withheld") for item in result["suggestions"]):
                base["limitations"].append("A rewrite was withheld by the numeric, incomplete-statement or source-needed policy; review comments remain available.")
            return {**base, **result, "status": "complete",
                    "elapsed_ms": round((time.perf_counter() - started) * 1000)}
        except Exception:
            return unavailable("The Groq review could not complete or returned invalid output. Check provider configuration or quota, or try a shorter passage.")
        finally:
            GPU_LOCK.release()
