"""Local writing workbench with an explicitly selected optional cloud coach."""

from __future__ import annotations

from contextlib import closing
from pathlib import Path
import asyncio
import threading
import time
import uuid
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, field_validator
from starlette.middleware.trustedhost import TrustedHostMiddleware

from . import __version__
from .corpus import ROOT, corpus_summary, default_corpus_path, open_readonly
from .matching import MAX_QUERY_TOKENS, analyze_sources, suggestions_for
from .research import ResearchBusy, ResearchDetector, ResearchUnavailable
from .coaching import WritingCoach
from .workbench import WorkbenchDetector
from .text import tokenize


MAX_TEXT_CHARS = 50_000
MAX_BODY_BYTES = 350_000
AUTHORSHIP = {
    "status": "unavailable", "score": None, "spans": [],
    "reason": "No detector has met the authorship accuracy requirements. Experimental model assessments are available separately and are not verified authorship conclusions.",
}


class AnalyzeInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    text: str = Field(min_length=1, max_length=MAX_TEXT_CHARS)
    request_id: str | None = Field(default=None, max_length=100, pattern=r"^[a-zA-Z0-9_.:-]+$")

    @field_validator("text")
    @classmethod
    def validate_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Paste a paragraph containing text.")
        if any(0xD800 <= ord(character) <= 0xDFFF for character in value):
            raise ValueError("Text contains invalid Unicode surrogate characters.")
        if "\x00" in value:
            raise ValueError("Text cannot contain null characters.")
        if len(tokenize(value)) > MAX_QUERY_TOKENS:
            raise ValueError(f"Use at most {MAX_QUERY_TOKENS:,} words.")
        return value


class CoachInput(AnalyzeInput):
    provider: Literal["local", "openai"] = "local"


class LocalRequestMiddleware:
    """Reject cross-origin browser calls and oversize bodies before parsing."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = dict(scope.get("headers", []))
        origin = headers.get(b"origin")
        host = headers.get(b"host", b"")
        if origin and origin not in (b"http://" + host, b"https://" + host):
            await JSONResponse({"detail": "Cross-origin requests are disabled for the local application."}, status_code=403)(scope, receive, send)
            return
        try:
            length = int(headers.get(b"content-length", b"0"))
        except ValueError:
            length = MAX_BODY_BYTES + 1
        if length < 0 or length > MAX_BODY_BYTES:
            await JSONResponse({"detail": "Request body is too large."}, status_code=413)(scope, receive, send)
            return
        # Buffer with a strict cap so chunked requests cannot bypass Content-Length.
        chunks = []
        size = 0
        while True:
            try:
                message = await asyncio.wait_for(receive(), timeout=10)
            except TimeoutError:
                await JSONResponse({"detail": "Request upload timed out."}, status_code=408)(scope, receive, send)
                return
            if message["type"] == "http.disconnect":
                return
            body = message.get("body", b"")
            size += len(body)
            if size > MAX_BODY_BYTES:
                await JSONResponse({"detail": "Request body is too large."}, status_code=413)(scope, receive, send)
                return
            chunks.append(body)
            if not message.get("more_body", False):
                break
        replayed = False

        async def replay():
            nonlocal replayed
            if not replayed:
                replayed = True
                return {"type": "http.request", "body": b"".join(chunks), "more_body": False}
            return await receive()

        async def safe_send(message):
            if message["type"] == "http.response.start":
                message["headers"] = list(message.get("headers", [])) + [
                    (b"x-content-type-options", b"nosniff"),
                    (b"referrer-policy", b"no-referrer"),
                    (b"cache-control", b"no-store"),
                    (b"content-security-policy", b"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'self'"),
                ]
            await send(message)

        await self.app(scope, replay, safe_send)


def create_app(corpus_path: str | Path | None = None, web_path: str | Path | None = None, *, research_detector: ResearchDetector | None = None,
               workbench_detector: WorkbenchDetector | None = None, writing_coach: WritingCoach | None = None) -> FastAPI:
    path = Path(corpus_path) if corpus_path is not None else default_corpus_path()
    frontend = Path(web_path) if web_path is not None else ROOT / "web"
    app = FastAPI(title="TuringTint Local", version=__version__, docs_url=None, redoc_url=None, openapi_url=None)
    scan_slots = threading.BoundedSemaphore(2)
    research = research_detector if research_detector is not None else ResearchDetector()
    workbench = workbench_detector if workbench_detector is not None else WorkbenchDetector(research_detector=research)
    coach = writing_coach if writing_coach is not None else WritingCoach()
    app.add_middleware(LocalRequestMiddleware)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "[::1]", "testserver"])

    @app.exception_handler(RequestValidationError)
    async def validation_error(_request, error):
        # Do not echo submitted paragraphs into diagnostics. This also handles
        # malformed Unicode that cannot be encoded in a JSON error response.
        details = [{"loc": [str(value).encode("utf-8", "backslashreplace").decode("utf-8") for value in item["loc"]],
                    "msg": item["msg"], "type": item["type"]} for item in error.errors()]
        return JSONResponse({"detail": details}, status_code=422)

    @app.get("/api/health")
    def health():
        return {"status": "ok", "version": __version__, "mode": "local", "authorship": AUTHORSHIP,
                "limits": {"max_text_characters": MAX_TEXT_CHARS, "max_words": MAX_QUERY_TOKENS},
                "privacy": "Analysis is local by default. Selecting OpenAI sends the passage to its API for review. The application does not save submitted paragraphs."}

    @app.get("/api/workbench/status")
    def workbench_status():
        return {"detector": {"available": (ROOT / ".cache/detector-models/mage/manifest.json").is_file()
                                         and (ROOT / "outputs/experiments/tfidf-v1/baseline.joblib").is_file(),
                             "validated": False}, "coaching": coach.status()}

    @app.post("/api/workbench/analyze")
    def workbench_analyze(payload: AnalyzeInput):
        try:
            result = workbench.analyze(payload.text)
        except ResearchBusy as error:
            raise HTTPException(status_code=409, detail=str(error)) from None
        except ResearchUnavailable as error:
            raise HTTPException(status_code=503, detail=str(error)) from None
        except Exception:
            raise HTTPException(status_code=503, detail="The model assessment could not finish. Try a shorter passage or restart the app.") from None
        return {**result, "request_id": payload.request_id or str(uuid.uuid4())}

    @app.post("/api/coach/review")
    def coach_review(payload: CoachInput):
        try:
            result = coach.review(payload.text, provider=payload.provider)
        except Exception:
            raise HTTPException(status_code=503, detail="The writing review could not finish. Try again shortly.") from None
        return {**result, "request_id": payload.request_id or str(uuid.uuid4())}

    @app.get("/api/corpus")
    def corpus():
        return corpus_summary(path)

    @app.post("/api/research/analyze")
    def research_analyze(payload: AnalyzeInput):
        try:
            result = research.analyze(payload.text)
        except ResearchBusy as error:
            raise HTTPException(status_code=409, detail=str(error)) from None
        except ResearchUnavailable as error:
            raise HTTPException(status_code=503, detail=str(error)) from None
        return {"request_id": payload.request_id or str(uuid.uuid4()), **result}

    @app.get("/api/example")
    def example():
        if corpus_summary(path)["status"] != "ready":
            return {"available": False, "text": "", "source": None}
        try:
            with closing(open_readonly(path)) as connection:
                document = connection.execute("SELECT title, url, text FROM documents ORDER BY document_id LIMIT 1").fetchone()
            tokens = tokenize(document["text"])
            end = tokens[min(149, len(tokens) - 1)].end
            return {"available": True, "text": document["text"][:end],
                    "source": {"title": document["title"], "url": document["url"]}}
        except Exception:
            return {"available": False, "text": "", "source": None}

    @app.post("/api/analyze")
    def analyze(payload: AnalyzeInput):
        started = time.perf_counter()
        if not scan_slots.acquire(blocking=False):
            raise HTTPException(status_code=429, detail="Two local scans are already running. Please retry shortly.")
        try:
            matching = analyze_sources(payload.text, path)
        finally:
            scan_slots.release()
        return {"request_id": payload.request_id or str(uuid.uuid4()), "text": payload.text,
                "offset_encoding": "utf-16", "authorship": AUTHORSHIP,
                "source_matching": matching, "suggestions": suggestions_for(matching["matches"]),
                "elapsed_ms": round((time.perf_counter() - started) * 1_000),
                "limitations": ["Source matches cover only this local library, not the entire internet.",
                                "Semantic paraphrase detection and validated AI authorship estimates are not yet available.",
                                "Wording overlap does not establish plagiarism; quotation, citation, and context require review."]}

    @app.get("/")
    def index():
        index_file = frontend / "index.html"
        if not index_file.is_file():
            raise HTTPException(status_code=503, detail="The local web interface has not been installed.")
        return FileResponse(index_file)

    if frontend.is_dir():
        app.mount("/static", StaticFiles(directory=frontend), name="static")
    return app


app = create_app()
