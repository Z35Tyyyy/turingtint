"""Bounded, deterministic wording overlap retrieval, not a plagiarism verdict."""

from __future__ import annotations

from collections import defaultdict
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
import json
import sqlite3
import time

from .corpus import corpus_summary, default_corpus_path, open_readonly
from .text import SHINGLE_SIZE, shingle, tokenize, utf16_offset


MAX_QUERY_TOKENS = 12_000
MAX_SEED_HITS = 12_000
MAX_CANDIDATES = 24
MAX_MATCHES = 40
MAX_EXPANSIONS = 3_000
MIN_EXACT_WORDS = 12
MIN_NEAR_WORDS = 18
ANALYSIS_SECONDS = 4.0
STOP_WORDS = set("a an and are as at be been being by can could did do does for from had has have how i if in into is it its may more most not of on or our should so than that the their them these they this those to was we were what when where which who will with would you your".split())


@dataclass(frozen=True)
class Block:
    query_start: int
    query_end: int
    source_start: int
    source_end: int
    matched_words: int

    @property
    def similarity(self) -> float:
        return 2 * self.matched_words / (self.query_end - self.query_start + self.source_end - self.source_start)


def _informative(tokens, block: Block) -> bool:
    words = {token.value for token in tokens[block.query_start:block.query_end]
             if token.value not in STOP_WORDS and len(token.value) > 3}
    return len(words) >= 5


def _extend(tokens, source_tokens, q: int, s: int, deadline: float) -> Block:
    qstart, sstart = q, s
    while qstart > 0 and sstart > 0 and tokens[qstart - 1].value == source_tokens[sstart - 1].value:
        qstart -= 1
        sstart -= 1
        if (q - qstart) % 256 == 0 and time.monotonic() > deadline:
            raise TimeoutError
    qend, send = q + SHINGLE_SIZE, s + SHINGLE_SIZE
    while qend < len(tokens) and send < len(source_tokens) and tokens[qend].value == source_tokens[send].value:
        qend += 1
        send += 1
        if (qend - q) % 256 == 0 and time.monotonic() > deadline:
            raise TimeoutError
    return Block(qstart, qend, sstart, send, qend - qstart)


def _near_blocks(blocks: list[Block], deadline: float) -> list[Block]:
    """Join nearby exact runs separated by at most four changed words per side."""
    by_start = defaultdict(list)
    for block in blocks:
        by_start[block.query_start].append(block)
    merged = []
    for start in blocks:
        if time.monotonic() > deadline:
            raise TimeoutError
        current = start
        for _ in range(20):
            choices = []
            for position in range(current.query_end, current.query_end + 5):
                for follow in by_start.get(position, []):
                    if (0 <= follow.source_start - current.source_end <= 4
                            and follow.query_end - start.query_start <= 250
                            and follow.source_end - start.source_start <= 250):
                        choices.append(follow)
            if not choices:
                break
            follow = max(choices, key=lambda candidate: candidate.matched_words)
            current = Block(start.query_start, follow.query_end, start.source_start, follow.source_end,
                            current.matched_words + follow.matched_words)
            if current.matched_words >= MIN_NEAR_WORDS and current.similarity >= 0.85:
                merged.append(current)
    return merged


def _contains(outer: Block, inner: Block) -> bool:
    return (outer.query_start <= inner.query_start and outer.query_end >= inner.query_end
            and outer.source_start <= inner.source_start and outer.source_end >= inner.source_end)


def analyze_sources(text: str, db_path: str | Path | None = None) -> dict:
    path = Path(db_path) if db_path is not None else default_corpus_path()
    summary = corpus_summary(path)
    result = {
        "status": "unavailable", "corpus": summary, "matches": [], "warnings": [],
        "method": "Case-normalized word overlap; 12+ exact words or 18+ aligned words with at least 85% overlap. Short/common fragments are suppressed.",
        "summary": "The local reference library is unavailable. No source comparison was completed.",
    }
    if summary["status"] not in {"ready", "empty"}:
        return result
    if summary["status"] == "empty":
        result["summary"] = "The local reference library is empty. No source comparison was completed."
        return result
    tokens = tokenize(text)
    if len(tokens) > MAX_QUERY_TOKENS:
        raise ValueError(f"Text exceeds the {MAX_QUERY_TOKENS:,}-word analysis limit.")
    if len(tokens) < MIN_EXACT_WORDS:
        result.update(status="insufficient_text", summary="At least 12 words are needed for this local overlap check.")
        return result

    deadline = time.monotonic() + ANALYSIS_SECONDS
    truncated = False
    completed_matches = []
    try:
        with closing(open_readonly(path)) as connection:
            connection.set_progress_handler(lambda: int(time.monotonic() > deadline), 1_000)
            query_seeds = defaultdict(list)
            for position in range(len(tokens) - SHINGLE_SIZE + 1):
                query_seeds[shingle(tokens, position)].append(position)
            fingerprints = sorted(query_seeds)
            candidates = defaultdict(list)
            total_hits = 0
            for start in range(0, len(fingerprints), 200):
                if time.monotonic() > deadline:
                    raise TimeoutError
                batch = fingerprints[start:start + 200]
                remaining = MAX_SEED_HITS - total_hits
                rows = connection.execute(
                    f"SELECT fingerprint, document_id, token_position FROM shingles WHERE fingerprint IN ({','.join('?' for _ in batch)}) LIMIT ?",
                    (*batch, remaining + 1),
                ).fetchall()
                if len(rows) > remaining:
                    truncated = True
                    rows = rows[:remaining]
                for row in rows:
                    candidates[row["document_id"]].append((row["fingerprint"], row["token_position"]))
                total_hits += len(rows)
                if total_hits >= MAX_SEED_HITS:
                    truncated = True
                    break

            ranked = sorted(candidates, key=lambda key: (-len({entry[0] for entry in candidates[key]}), key))
            if len(ranked) > MAX_CANDIDATES:
                truncated = True
            expansions = 0
            for document_id in ranked[:MAX_CANDIDATES]:
                if time.monotonic() > deadline:
                    raise TimeoutError
                document = connection.execute("SELECT * FROM documents WHERE document_id = ?", (document_id,)).fetchone()
                if document is None:
                    continue
                source_text = document["text"]
                source_tokens = tokenize(source_text)
                blocks = set()
                diagonals = defaultdict(list)
                for fingerprint, source_position in candidates[document_id]:
                    for query_position in query_seeds[fingerprint]:
                        if time.monotonic() > deadline:
                            raise TimeoutError
                        if expansions >= MAX_EXPANSIONS:
                            truncated = True
                            break
                        diagonal = query_position - source_position
                        if any(left <= query_position < right for left, right in diagonals[diagonal]):
                            continue
                        # Never rely on a hash match without confirming actual words.
                        if ([t.value for t in tokens[query_position:query_position + SHINGLE_SIZE]]
                                != [t.value for t in source_tokens[source_position:source_position + SHINGLE_SIZE]]):
                            continue
                        block = _extend(tokens, source_tokens, query_position, source_position, deadline)
                        expansions += 1
                        blocks.add(block)
                        diagonals[diagonal].append((block.query_start, block.query_end))
                    if expansions >= MAX_EXPANSIONS:
                        break
                if len(blocks) > 400:
                    truncated = True
                bounded_blocks = sorted(blocks, key=lambda block: (-block.matched_words, block.query_start, block.source_start))[:400]
                exact = [block for block in bounded_blocks if block.matched_words >= MIN_EXACT_WORDS and _informative(tokens, block)]
                near = [block for block in _near_blocks(bounded_blocks, deadline) if _informative(tokens, block)]
                accepted = []
                for block in sorted(set(exact + near), key=lambda b: (-b.matched_words, -b.similarity, b.query_start, b.source_start)):
                    if not any(_contains(existing, block) for existing in accepted):
                        accepted.append(block)
                metadata = json.loads(document["metadata_json"])
                for block in accepted:
                    qs, qe = tokens[block.query_start].start, tokens[block.query_end - 1].end
                    ss, se = source_tokens[block.source_start].start, source_tokens[block.source_end - 1].end
                    completed_matches.append({
                        "kind": "exact_text_overlap" if block.similarity == 1 else "near_exact_text_overlap",
                        "query_start": utf16_offset(text, qs), "query_end": utf16_offset(text, qe),
                        "query_text": text[qs:qe], "source_start": utf16_offset(source_text, ss),
                        "source_end": utf16_offset(source_text, se), "source_text": source_text[ss:se],
                        "similarity": round(block.similarity, 4), "matched_words": block.matched_words,
                        "source": {"document_id": document_id, "title": document["title"], "url": document["url"],
                                   "license_id": document["license_id"], "license_url": document["license_url"],
                                   "source_provider": document["source_provider"],
                                   "attribution": metadata.get("attribution", ""),
                                   "license_evidence": metadata.get("license_evidence", "")},
                    })
    except (TimeoutError, sqlite3.OperationalError):
        truncated = True
        result["warnings"].append("The comparison reached a time or database resource limit; some matches may be missing.")
    except (sqlite3.Error, ValueError, TypeError, KeyError):
        result["status"] = "error"
        result["summary"] = "The local reference index could not be analyzed. No complete comparison is available."
        return result

    completed_matches.sort(key=lambda item: (-item["matched_words"], -item["similarity"], item["query_start"], item["source"]["document_id"]))
    if len(completed_matches) > MAX_MATCHES:
        truncated = True
    matches = sorted(completed_matches[:MAX_MATCHES], key=lambda item: (item["query_start"], -item["query_end"]))
    for index, match in enumerate(matches):
        match["id"] = f"match-{index + 1}"
    if truncated:
        result["warnings"].append("Results are partial because comparison limits were reached. Absence of a match is inconclusive.")
    result.update(status="partial" if truncated else "complete", matches=matches)
    if matches:
        result["summary"] = "Matching wording was found in the local reference library. Review sources and attribution; overlap alone does not establish plagiarism."
    elif truncated:
        result["summary"] = "No source match was returned by this incomplete local comparison."
    else:
        result["summary"] = "No source match found in the local corpus. This does not establish originality or exclude paraphrased reuse."
    return result


def suggestions_for(matches: list[dict]) -> list[dict]:
    return [{
        "id": f"suggestion-{index + 1}", "match_id": match["id"],
        "start": match["query_start"], "end": match["query_end"],
        "title": "Review quotation and attribution",
        "reason": f"This passage shares wording with {match['source']['title']}.",
        "action": "Check whether this wording is already correctly quoted and cited. If you reuse it, preserve its meaning and credit the source; add your own analysis where it contributes. This does not predict an AI score change.",
    } for index, match in enumerate(matches)]
