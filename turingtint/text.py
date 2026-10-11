"""Word tokenization retaining offsets into the unmodified input."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re
import unicodedata


# Combining accents stay attached to their original letters, so NFC and NFD
# spellings compare equally without changing the displayed text or its offsets.
WORD_UNIT = r"[^\W_][\u0300-\u036f\u1ab0-\u1aff\u1dc0-\u1dff\u20d0-\u20ff\ufe20-\ufe2f]*"
WORD_RE = re.compile(rf"(?:{WORD_UNIT})+(?:['’](?:{WORD_UNIT})+)*", re.UNICODE)
SHINGLE_SIZE = 5
SOURCE_STRIDE = 5


@dataclass(frozen=True, slots=True)
class Token:
    value: str
    start: int
    end: int


def tokenize(text: str) -> list[Token]:
    return [
        Token(unicodedata.normalize("NFKC", match.group()).casefold().replace("’", "'"),
              match.start(), match.end())
        for match in WORD_RE.finditer(text)
    ]


def shingle(tokens: list[Token], start: int) -> str:
    normalized = "\x1f".join(t.value for t in tokens[start:start + SHINGLE_SIZE])
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:24]


def utf16_offset(text: str, codepoint_offset: int) -> int:
    """Browser String.slice uses UTF-16 code units, unlike Python's indices."""
    return len(text[:codepoint_offset].encode("utf-16-le")) // 2


def utf16_slice(text: str, start: int, end: int) -> str:
    return text.encode("utf-16-le")[start * 2:end * 2].decode("utf-16-le")
