"""Tests for improvements introduced in the code-review pass.

Covers:
- config.py constants and environment-variable overrides
- _categorize_error() helper
- File-size validation in extract_source_chapters()
- PronunciationDict.apply()
- ensure_manifest_defaults() back-filling
- build_manifest() schema
- estimate_generation_seconds() behaviour
- slugify() edge cases
- format_eta() output
"""
import os
import tempfile
import unittest
from pathlib import Path

from audiobook_creator_v7 import (
    PronunciationDict,
    _categorize_error,
    build_manifest,
    ensure_manifest_defaults,
    estimate_generation_seconds,
    extract_source_chapters,
    format_eta,
    slugify,
)


class TestCategorizeError(unittest.TestCase):
    def test_network_error(self):
        err = _categorize_error(Exception("connection refused"))
        self.assertIn("Network error", err)

    def test_file_error(self):
        err = _categorize_error(Exception("no such file or directory"))
        self.assertIn("File error", err)

    def test_ffmpeg_error(self):
        err = _categorize_error(Exception("ffmpeg returned exit code 1"))
        self.assertIn("Assembly error", err)

    def test_generic_error_passthrough(self):
        msg = "something completely unexpected"
        err = _categorize_error(Exception(msg))
        self.assertEqual(err, msg)

    def test_tts_error(self):
        err = _categorize_error(Exception("kokoro voice engine raised an exception"))
        self.assertIn("TTS error", err)

    def test_timeout(self):
        err = _categorize_error(Exception("connection timed out"))
        self.assertIn("Network error", err)


class TestFileSizeValidation(unittest.TestCase):
    def test_oversized_file_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            big_file = Path(tmp) / "huge.txt"
            # Write a file slightly over the 500 MB default limit via env var trick.
            # We override ABM_MAX_UPLOAD_FILE_BYTES to a tiny value instead of
            # writing 500 MB to disk.
            import audiobook_creator_v7 as abm
            original_limit = abm.MAX_UPLOAD_FILE_BYTES
            abm.MAX_UPLOAD_FILE_BYTES = 10  # 10 bytes
            try:
                big_file.write_bytes(b"A" * 20)  # 20 bytes > 10
                with self.assertRaises(ValueError) as ctx:
                    extract_source_chapters(input_path=str(big_file))
                self.assertIn("MB", str(ctx.exception))
            finally:
                abm.MAX_UPLOAD_FILE_BYTES = original_limit

    def test_missing_file_raises(self):
        with self.assertRaises(ValueError) as ctx:
            extract_source_chapters(input_path="/nonexistent/file.txt")
        self.assertIn("not found", str(ctx.exception).lower())

    def test_no_input_raises(self):
        with self.assertRaises(ValueError):
            extract_source_chapters()

    def test_inline_text_accepted(self):
        chapters, meta, _, source_type = extract_source_chapters(raw_text="Hello world.\n\nSecond paragraph.")
        self.assertEqual(source_type, "text")
        self.assertGreater(len(chapters), 0)


class TestPronunciationDict(unittest.TestCase):
    def test_whole_word_replacement(self):
        pd = PronunciationDict({"read": "reed"})
        result = pd.apply("I read the book.")
        # "read" as a standalone word should be replaced
        self.assertIn("reed", result)
        self.assertNotIn(" read ", result)

    def test_partial_word_not_replaced(self):
        pd = PronunciationDict({"read": "reed"})
        # "reading" contains "read" but the word boundary prevents replacement
        result = pd.apply("I was reading a lot.")
        self.assertIn("reading", result)
        self.assertNotIn("reeding", result)

    def test_case_insensitive(self):
        pd = PronunciationDict({"worcestershire": "Wooster-sher"})
        result = pd.apply("Add Worcestershire sauce.")
        self.assertIn("Wooster-sher", result)

    def test_empty_overrides(self):
        pd = PronunciationDict()
        self.assertEqual(pd.apply("hello"), "hello")


class TestEnsureManifestDefaults(unittest.TestCase):
    def test_empty_manifest_gets_all_defaults(self):
        m = ensure_manifest_defaults({})
        self.assertIn("settings", m)
        self.assertIn("chapters", m)
        self.assertIn("progress", m)
        self.assertIn("runtime", m)
        self.assertEqual(m["runtime"]["state"], "idle")

    def test_existing_keys_not_overwritten(self):
        m = ensure_manifest_defaults({"runtime": {"state": "generated", "message": "done"}})
        self.assertEqual(m["runtime"]["state"], "generated")
        self.assertEqual(m["runtime"]["message"], "done")

    def test_assembly_sub_keys_present(self):
        m = ensure_manifest_defaults({})
        assembly = m["runtime"]["assembly"]
        for key in ("concat_done", "music_mixed", "speed_adjusted", "normalized", "output_done"):
            self.assertIn(key, assembly)


class TestBuildManifest(unittest.TestCase):
    def test_returns_correct_schema(self):
        chapters = [
            {"title": "Ch 1", "segments": [{"status": "cached"}, {"status": "pending"}]},
        ]
        m = build_manifest(settings={"tts_engine": "edge-tts"}, chapters=chapters, book={"title": "Test"})
        self.assertEqual(m["book"]["title"], "Test")
        self.assertEqual(m["progress"]["total_segments"], 2)
        self.assertEqual(m["progress"]["completed_segments"], 1)
        self.assertEqual(m["runtime"]["state"], "idle")

    def test_empty_chapters(self):
        m = build_manifest(settings={}, chapters=[], book={})
        self.assertEqual(m["progress"]["total_segments"], 0)
        self.assertEqual(m["progress"]["completed_segments"], 0)


class TestEstimateGenerationSeconds(unittest.TestCase):
    def test_cloud_engine_faster(self):
        cloud_secs = estimate_generation_seconds(1000, "edge-tts")
        local_secs = estimate_generation_seconds(1000, "kokoro")
        self.assertLess(cloud_secs, local_secs)

    def test_zero_chars(self):
        self.assertEqual(estimate_generation_seconds(0, "edge-tts"), 0)

    def test_reasonable_range(self):
        secs = estimate_generation_seconds(28000, "edge-tts")
        # 28000 chars / 28 cps = 1000s
        self.assertEqual(secs, 1000)


class TestSlugify(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(slugify("Hello World"), "Hello_World")

    def test_special_chars_removed(self):
        slug = slugify("My Book: A Story!")
        self.assertNotIn(":", slug)
        self.assertNotIn("!", slug)

    def test_empty_returns_fallback(self):
        self.assertEqual(slugify("", fallback="default"), "default")

    def test_strips_leading_trailing_dots(self):
        slug = slugify("...book...")
        self.assertFalse(slug.startswith("."))
        self.assertFalse(slug.endswith("."))


class TestFormatEta(unittest.TestCase):
    def test_seconds_only(self):
        self.assertEqual(format_eta(45), "00:45")

    def test_minutes_and_seconds(self):
        self.assertEqual(format_eta(125), "02:05")

    def test_hours(self):
        self.assertEqual(format_eta(3661), "01:01:01")

    def test_zero(self):
        self.assertEqual(format_eta(0), "00:00")

    def test_negative_treated_as_zero(self):
        self.assertEqual(format_eta(-10), "00:00")


class TestConfig(unittest.TestCase):
    """Verify that config.py exposes the expected constants."""

    def test_config_importable(self):
        import config
        self.assertTrue(hasattr(config, "APP_VERSION"))
        self.assertTrue(hasattr(config, "DEFAULT_FFMPEG_TIMEOUT_S"))
        self.assertTrue(hasattr(config, "MAX_UPLOAD_FILE_BYTES"))
        self.assertTrue(hasattr(config, "GRADIO_SERVER_PORT"))

    def test_config_env_override(self):
        os.environ["ABM_FFMPEG_TIMEOUT_S"] = "999"
        # Re-import to pick up env var — we test the value parsing logic directly.
        import config as cfg
        import importlib
        importlib.reload(cfg)
        self.assertEqual(cfg.DEFAULT_FFMPEG_TIMEOUT_S, 999)
        del os.environ["ABM_FFMPEG_TIMEOUT_S"]
        importlib.reload(cfg)

    def test_upload_limit_default(self):
        import config as cfg
        import importlib
        importlib.reload(cfg)
        self.assertEqual(cfg.MAX_UPLOAD_FILE_BYTES, 500 * 1024 * 1024)


if __name__ == "__main__":
    unittest.main()
