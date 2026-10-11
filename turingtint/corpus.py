"""SQLite reference library with license and provenance metadata.

Importers call ingest_document; readers open the database read-only. Submitted
analysis text is never inserted into this library.
"""

from __future__ import annotations

from datetime import datetime, timezone
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import sqlite3
from urllib.parse import urlsplit

from .text import SHINGLE_SIZE, SOURCE_STRIDE, shingle, tokenize


ROOT = Path(__file__).resolve().parent.parent
SCHEMA_VERSION = 1
MAX_DOCUMENT_CHARS = 1_000_000
ALLOWED_LICENSES = {"CC0-1.0", "CC-BY-2.0", "CC-BY-2.5", "CC-BY-3.0", "CC-BY-4.0"}


def default_corpus_path() -> Path:
    return Path(os.environ.get("TURINGTINT_CORPUS", str(ROOT / "data" / "reference.sqlite")))


def _validate_url(url: str, *, optional: bool = False) -> None:
    if optional and not url:
        return
    try:
        parts = urlsplit(url)
        valid = parts.scheme in {"http", "https"} and parts.hostname and not parts.username and not parts.password
        if not valid or any(character.isspace() or ord(character) < 32 for character in url):
            raise ValueError("Source URLs must be HTTP(S), without credentials or whitespace.")
    except (TypeError, ValueError) as exc:
        raise ValueError("Source URLs must be HTTP(S), without credentials or whitespace.") from exc


def _initialize(connection: sqlite3.Connection) -> None:
    version = connection.execute("PRAGMA user_version").fetchone()[0]
    if version not in {0, SCHEMA_VERSION}:
        raise ValueError("Unsupported reference corpus schema version.")
    connection.executescript("""
        CREATE TABLE IF NOT EXISTS documents (
            document_id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            text TEXT NOT NULL,
            url TEXT NOT NULL,
            license_id TEXT NOT NULL,
            license_url TEXT NOT NULL,
            source_provider TEXT NOT NULL,
            metadata_json TEXT NOT NULL,
            word_count INTEGER NOT NULL,
            content_sha256 TEXT NOT NULL,
            indexed_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS shingles (
            fingerprint TEXT NOT NULL,
            document_id TEXT NOT NULL REFERENCES documents(document_id) ON DELETE CASCADE,
            token_position INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS shingles_fingerprint ON shingles(fingerprint);
        CREATE INDEX IF NOT EXISTS shingles_document ON shingles(document_id);
        PRAGMA user_version = 1;
    """)


def ingest_document(
    db_path: str | Path,
    *,
    document_id: str,
    title: str,
    text: str,
    url: str,
    license_id: str,
    license_url: str = "",
    source_provider: str = "local",
    metadata: dict | None = None,
) -> dict:
    """Atomically insert/update a licensed reference; reindex updates by ID.

    License IDs are checked against the project's initial allowlist. Importers
    remain responsible for verifying article-specific rights and storing the
    evidence in metadata; a supplied license string is not a rights audit.
    """
    if not isinstance(document_id, str) or not document_id.strip() or len(document_id) > 256:
        raise ValueError("document_id must contain 1–256 characters.")
    if not isinstance(title, str) or not title.strip() or len(title) > 2_000:
        raise ValueError("title must contain 1–2,000 characters.")
    if not isinstance(text, str) or not text.strip() or len(text) > MAX_DOCUMENT_CHARS:
        raise ValueError(f"Reference text must contain 1–{MAX_DOCUMENT_CHARS:,} characters.")
    if license_id not in ALLOWED_LICENSES:
        raise ValueError("Reference license is outside the initial CC BY/CC0 allowlist.")
    _validate_url(url)
    _validate_url(license_url, optional=True)
    if not isinstance(source_provider, str) or len(source_provider) > 100:
        raise ValueError("source_provider must be a short string.")
    if metadata is not None and not isinstance(metadata, dict):
        raise ValueError("metadata must be a JSON object.")
    encoded_metadata = json.dumps(metadata or {}, ensure_ascii=False, allow_nan=False)
    if len(encoded_metadata) > 100_000:
        raise ValueError("Reference metadata is too large.")
    tokens = tokenize(text)
    if len(tokens) < SHINGLE_SIZE:
        raise ValueError("A reference must contain at least five words.")
    content_sha256 = hashlib.sha256(text.encode("utf-8")).hexdigest()
    indexed_at = datetime.now(timezone.utc).isoformat()
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path, timeout=10)) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        _initialize(connection)
        connection.execute("DELETE FROM documents WHERE document_id = ?", (document_id,))
        connection.execute(
            "INSERT INTO documents VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (document_id, title, text, url, license_id, license_url, source_provider,
             encoded_metadata, len(tokens), content_sha256, indexed_at),
        )
        connection.executemany(
            "INSERT INTO shingles VALUES (?, ?, ?)",
            ((shingle(tokens, position), document_id, position)
             for position in range(0, len(tokens) - SHINGLE_SIZE + 1, SOURCE_STRIDE)),
        )
        connection.commit()
    return {"document_id": document_id, "word_count": len(tokens), "content_sha256": content_sha256}


def open_readonly(path: str | Path) -> sqlite3.Connection:
    connection = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True, timeout=1)
    connection.row_factory = sqlite3.Row
    try:
        version = connection.execute("PRAGMA user_version").fetchone()[0]
    except sqlite3.Error:
        connection.close()
        raise
    if version != SCHEMA_VERSION:
        connection.close()
        raise ValueError("Unsupported reference corpus schema version.")
    return connection


def corpus_summary(path: str | Path | None = None) -> dict:
    path = Path(path) if path is not None else default_corpus_path()
    empty = {"document_count": 0, "word_count": 0, "licenses": {}, "updated_at": None}
    if not path.is_file():
        return {"status": "missing", **empty,
                "scope": "No local reference library has been imported."}
    try:
        with closing(open_readonly(path)) as connection:
            row = connection.execute(
                "SELECT COUNT(*), COALESCE(SUM(word_count), 0), MAX(indexed_at) FROM documents"
            ).fetchone()
            licenses = dict(connection.execute(
                "SELECT license_id, COUNT(*) FROM documents GROUP BY license_id ORDER BY license_id"
            ).fetchall())
        return {"status": "ready" if row[0] else "empty", "document_count": row[0],
                "word_count": row[1], "licenses": licenses, "updated_at": row[2],
                "scope": "Only documents in this local reference library are compared; the internet is not searched."}
    except (sqlite3.Error, ValueError):
        return {"status": "error", **empty,
                "scope": "The local reference library could not be read."}
