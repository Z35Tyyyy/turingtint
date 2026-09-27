"""Contract and retrieval regression tests; these do not measure AI accuracy."""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from turingtint.app import MAX_BODY_BYTES, create_app
from turingtint.corpus import corpus_summary, ingest_document
from turingtint.matching import analyze_sources
from turingtint.text import utf16_slice


PASSAGE = (
    "Researchers examined the relationship between seasonal temperature variations and freshwater "
    "biodiversity across several independently monitored ecological reserves. Measurements collected "
    "during repeated field visits revealed substantial differences in microbial abundance, nutrient "
    "availability, dissolved oxygen concentrations, and population recovery following prolonged drought."
)


class BackendTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "reference.sqlite"
        self.add_document()
        self.client = TestClient(create_app(self.path))
        self.addCleanup(self.client.close)

    def add_document(self, **changes):
        values = dict(document_id="reference-1", title="Seasonal ecology", text=PASSAGE,
                      url="https://example.org/paper", license_id="CC-BY-4.0",
                      license_url="https://creativecommons.org/licenses/by/4.0/",
                      metadata={"license_evidence": "Fixture released under CC BY 4.0", "attribution": "Fixture author"})
        values.update(changes)
        return ingest_document(self.path, **values)

    def analyze(self, text):
        response = self.client.post("/api/analyze", json={"text": text, "request_id": "test-1"})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_exact_passage_returns_real_source_and_null_authorship(self):
        result = self.analyze(PASSAGE)
        self.assertEqual(result["request_id"], "test-1")
        self.assertEqual(result["authorship"]["status"], "unavailable")
        self.assertIsNone(result["authorship"]["score"])
        self.assertEqual(result["authorship"]["spans"], [])
        source = result["source_matching"]
        self.assertEqual(source["status"], "complete")
        self.assertEqual(len(source["matches"]), 1)
        match = source["matches"][0]
        self.assertEqual(match["query_text"], PASSAGE[:-1])
        self.assertEqual(match["source_text"], PASSAGE[:-1])
        self.assertEqual(match["kind"], "exact_text_overlap")
        self.assertEqual(match["source"]["license_id"], "CC-BY-4.0")
        self.assertIn("does not establish plagiarism", source["summary"])
        self.assertEqual(result["suggestions"][0]["match_id"], match["id"])

    def test_utf16_ranges_recover_original_text_after_emoji(self):
        prefix = "🧪 🌍 Student note: "
        text = prefix + PASSAGE
        result = self.analyze(text)
        match = result["source_matching"]["matches"][0]
        self.assertEqual(match["query_start"], len(prefix) + 2)
        self.assertEqual(utf16_slice(text, match["query_start"], match["query_end"]), match["query_text"])
        self.assertEqual(utf16_slice(PASSAGE, match["source_start"], match["source_end"]), match["source_text"])

    def test_source_offsets_also_use_utf16(self):
        self.add_document(text="🧪 Preface. " + PASSAGE)
        result = self.analyze(PASSAGE)
        match = result["source_matching"]["matches"][0]
        self.assertEqual(utf16_slice("🧪 Preface. " + PASSAGE, match["source_start"], match["source_end"]), match["source_text"])

    def test_case_and_punctuation_preserve_query_display(self):
        changed = PASSAGE.upper().replace(" ", "  ").replace(",", " —")
        result = self.analyze(changed)
        match = result["source_matching"]["matches"][0]
        self.assertEqual(match["kind"], "exact_text_overlap")
        self.assertEqual(utf16_slice(changed, match["query_start"], match["query_end"]), match["query_text"])
        self.assertNotEqual(match["query_text"], match["source_text"])

    def test_canonical_unicode_accents_match_without_offset_changes(self):
        self.add_document(text="Café " + PASSAGE)
        query = "Cafe\u0301 " + PASSAGE
        match = self.analyze(query)["source_matching"]["matches"][0]
        self.assertEqual(match["query_start"], 0)
        self.assertEqual(match["kind"], "exact_text_overlap")
        self.assertEqual(utf16_slice(query, match["query_start"], match["query_end"]), query[:-1])

    def test_light_word_change_is_near_exact_evidence(self):
        changed = PASSAGE.replace("Measurements", "Observations")
        result = self.analyze(changed)
        match = result["source_matching"]["matches"][0]
        self.assertEqual(match["kind"], "near_exact_text_overlap")
        self.assertGreaterEqual(match["similarity"], 0.85)
        self.assertLess(match["similarity"], 1)
        self.assertIn("Observations", match["query_text"])
        self.assertIn("Measurements", match["source_text"])

    def test_common_and_short_phrases_are_suppressed(self):
        common = "the aim of this study was to investigate the effects of this on the other study and the study"
        self.add_document(document_id="common", text=common)
        self.assertEqual(self.analyze(common)["source_matching"]["matches"], [])
        self.assertEqual(self.analyze("A short sentence.")["source_matching"]["status"], "insufficient_text")

    def test_unrelated_text_is_local_no_match_not_originality(self):
        result = self.analyze("Historians study medieval trade networks using archival correspondence, taxation records, archaeological discoveries and documented commercial relationships between cities.")
        self.assertEqual(result["source_matching"]["matches"], [])
        self.assertIn("does not establish originality", result["source_matching"]["summary"])

    def test_missing_and_corrupt_corpora_do_not_report_clean_scan(self):
        missing = Path(self.directory.name) / "missing.sqlite"
        result = analyze_sources(PASSAGE, missing)
        self.assertEqual(result["status"], "unavailable")
        self.assertFalse(missing.exists())
        missing.write_text("not a SQLite database", encoding="utf-8")
        self.assertEqual(corpus_summary(missing)["status"], "error")
        self.assertEqual(analyze_sources(PASSAGE, missing)["status"], "unavailable")

    def test_html_is_returned_as_data_and_security_headers_present(self):
        self.add_document(title='<img src=x onerror="alert(1)">')
        result = self.analyze("<script>alert(1)</script> " + PASSAGE)
        self.assertIn("<script>", result["text"])
        self.assertEqual(result["source_matching"]["matches"][0]["source"]["title"], '<img src=x onerror="alert(1)">')
        response = self.client.get("/api/health")
        self.assertEqual(response.headers["x-content-type-options"], "nosniff")
        self.assertIn("script-src 'self'", response.headers["content-security-policy"])
        self.assertEqual(response.headers["cache-control"], "no-store")

    def test_validation_rejects_blank_oversize_wrong_type_and_surrogates(self):
        for value in ("", "   \n\t", "a" * 50_001, 12, "bad\ud800text", "null\x00byte"):
            with self.subTest(value_type=type(value).__name__):
                response = self.client.post("/api/analyze", content=__import__("json").dumps({"text": value}),
                                            headers={"content-type": "application/json"})
                self.assertEqual(response.status_code, 422)
        self.assertEqual(self.client.post("/api/analyze", json={"text": PASSAGE, "unknown": True}).status_code, 422)

    def test_large_body_and_untrusted_browser_origins_are_rejected(self):
        self.assertEqual(self.client.post("/api/analyze", content=b"x" * (MAX_BODY_BYTES + 1)).status_code, 413)
        self.assertEqual(self.client.post("/api/analyze", json={"text": PASSAGE},
                                         headers={"Origin": "https://malicious.example"}).status_code, 403)
        self.assertEqual(self.client.get("/api/health", headers={"Host": "evil.example"}).status_code, 400)

    def test_reference_updates_replace_shingles_and_preserve_document_count(self):
        other = "Astronomers calibrated orbital measurements using independent observatory records and compared distant stellar spectra across multiple wavelengths during extended monitoring campaigns."
        self.add_document(text=other)
        self.assertEqual(corpus_summary(self.path)["document_count"], 1)
        self.assertEqual(self.analyze(PASSAGE)["source_matching"]["matches"], [])
        self.assertEqual(len(self.analyze(other)["source_matching"]["matches"]), 1)

    def test_disallowed_license_and_executable_url_are_rejected(self):
        with self.assertRaises(ValueError):
            self.add_document(license_id="CC-BY-NC-SA-4.0")
        for url in ("javascript:alert(1)", "https://user:secret@example.org", "https://example.org/\nattack"):
            with self.assertRaises(ValueError):
                self.add_document(url=url)

    def test_paragraph_is_not_persisted_and_network_is_not_used(self):
        before = self.path.read_bytes()
        with patch("socket.socket.connect", side_effect=AssertionError("No networking is permitted")):
            self.assertTrue(analyze_sources(PASSAGE, self.path)["matches"])
        self.analyze(PASSAGE)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(sorted(p.name for p in Path(self.directory.name).iterdir()), ["reference.sqlite"])

    def test_example_and_health_contract(self):
        example = self.client.get("/api/example").json()
        self.assertTrue(example["available"])
        self.assertTrue(self.analyze(example["text"])["source_matching"]["matches"])
        self.assertEqual(self.client.get("/api/health").json()["mode"], "local")
        self.assertEqual(self.client.get("/docs").status_code, 404)

    def test_exceeded_time_budget_reports_partial(self):
        with patch("turingtint.matching.ANALYSIS_SECONDS", -1):
            result = self.analyze(PASSAGE)["source_matching"]
        self.assertEqual(result["status"], "partial")
        self.assertTrue(result["warnings"])
        self.assertIn("incomplete", result["summary"])


if __name__ == "__main__":
    unittest.main()
