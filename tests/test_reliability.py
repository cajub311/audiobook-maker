import tempfile
import unittest
from pathlib import Path
import wave
import contextlib
import asyncio
from unittest.mock import patch

from audiobook_creator_v7 import (
    AudioCache,
    build_atempo_filter,
    choose_resume_project_id,
    create_tts_engine,
    format_quick_mode_error,
    humanize_generate_progress_desc,
    load_manifest,
    manifest_has_generation_errors,
    normalize_quick_output_format_label,
    save_manifest,
    stage_generate,
    validate_safe_http_url,
    validate_local_input_file,
)
from nlp.dialogue import detect_all_dialogue, detect_dialogue_with_strategy, normalize_dialogue_strategy
from nlp.pronunciation import PronunciationDict


def write_silence_wav(path: Path, duration_s: float = 0.5, sample_rate: int = 24000) -> None:
    frames = int(sample_rate * duration_s)
    with contextlib.closing(wave.open(str(path), "wb")) as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes((0).to_bytes(2, byteorder="little", signed=True) * frames)


class ReliabilityTests(unittest.TestCase):
    def test_manifest_backup_recovery(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest_path = Path(tmp) / "m.json"
            original = {"book": {"title": "T"}, "runtime": {"state": "idle"}}
            save_manifest(original, manifest_path)
            manifest_path.write_text("{broken json", encoding="utf-8")
            recovered = load_manifest(manifest_path)
            self.assertEqual(recovered["book"]["title"], "T")

    def test_speed_post_process_cache_reuse(self):
        with tempfile.TemporaryDirectory() as tmp:
            wav = Path(tmp) / "sample.wav"
            write_silence_wav(wav)
            cache = AudioCache(cache_dir=tmp, max_size_mb=50)
            cache.put(
                text="hello",
                voice="v1",
                engine="kokoro",
                speed=1.2,
                audio_path=str(wav),
                duration=0.5,
                pronunciation_hash="x",
                speed_mode="post_process",
            )
            hit = cache.get(
                text="hello",
                voice="v1",
                engine="kokoro",
                speed=0.8,
                pronunciation_hash="x",
                speed_mode="post_process",
            )
            self.assertIsNotNone(hit)

    def test_atempo_filter_builder(self):
        self.assertEqual(build_atempo_filter(1.0), "anull")
        chain = build_atempo_filter(3.0)
        self.assertTrue(chain.startswith("atempo="))
        self.assertIn(",", chain)

    def test_validate_safe_http_url_rejects_private_hosts(self):
        with self.assertRaises(ValueError):
            validate_safe_http_url("http://127.0.0.1:8080")
        with self.assertRaises(ValueError):
            validate_safe_http_url("http://localhost:8000")

    def test_stage_generate_cached_only_sets_generated_state(self):
        manifest = {
            "settings": {"tts_engine": "kokoro"},
            "chapters": [{"segments": [{"status": "cached", "cache_file": "x"}], "status": "complete"}],
            "progress": {"generation_started": None},
            "runtime": {"state": "idle", "message": ""},
        }
        out = asyncio.run(stage_generate(manifest))
        self.assertEqual(out.get("runtime", {}).get("state"), "generated")

    def test_resume_selector_prefers_selected_or_last(self):
        inventory = {"local::/tmp/a.json": {"manifest_path": "/tmp/a.json"}}
        selected = choose_resume_project_id(inventory, "local::/tmp/a.json")
        self.assertEqual(selected, "local::/tmp/a.json")

    def test_manifest_error_when_cached_file_missing(self):
        manifest = {"chapters": [{"segments": [{"status": "cached", "cache_file": "/definitely/missing.mp3"}]}]}
        self.assertTrue(manifest_has_generation_errors(manifest))

    def test_pdf_size_validation_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake_pdf = Path(tmp) / "book.pdf"
            fake_pdf.write_bytes(b"x" * 12)
            with patch("audiobook_creator_v7.MAX_UPLOAD_FILE_BYTES", 10):
                with self.assertRaises(ValueError):
                    validate_local_input_file(fake_pdf)

    def test_upload_size_validation_applies_to_epub_not_only_pdf(self):
        with tempfile.TemporaryDirectory() as tmp:
            big_epub = Path(tmp) / "book.epub"
            big_epub.write_bytes(b"x" * 120)
            with patch("audiobook_creator_v7.MAX_UPLOAD_FILE_BYTES", 10):
                with self.assertRaises(ValueError) as ctx:
                    validate_local_input_file(big_epub)
                self.assertIn("MB", str(ctx.exception))

    def test_dialogue_detection_regex_path(self):
        text = '"Hello there," Alice said.\n\n"Hi," Bob said.'
        found = detect_all_dialogue(text)
        speakers = [item.get("speaker") for item in found if item.get("speaker")]
        self.assertIn("Alice", speakers)

    def test_dialogue_strategy_normalization(self):
        self.assertEqual(normalize_dialogue_strategy("Regex only (faster)"), "regex_only")
        self.assertEqual(normalize_dialogue_strategy("Quotes only"), "quotes_only")
        self.assertEqual(normalize_dialogue_strategy("Auto"), "auto")

    def test_dialogue_strategy_quotes_only(self):
        text = '"Hello there," Alice said.'
        found = detect_dialogue_with_strategy(text, "quotes_only")
        self.assertTrue(found)
        self.assertIsNone(found[0].get("speaker"))

    def test_dialogue_quotes_detect_multilingual_marks(self):
        text = "«Bonjour tout le monde» she wrote."
        found = detect_dialogue_with_strategy(text, "quotes_only")
        self.assertTrue(found)
        self.assertEqual(found[0].get("quote_style"), "guillemet")

    def test_dialogue_confidence_present(self):
        text = '"Hello there," Alice said.'
        found = detect_all_dialogue(text)
        self.assertTrue(found)
        confidence = float(found[0].get("confidence", 0.0))
        self.assertGreater(confidence, 0.0)
        self.assertLessEqual(confidence, 1.0)

    def test_quick_output_format_normalization(self):
        self.assertEqual(
            normalize_quick_output_format_label("M4B"),
            "M4B (chapter bookmarks)",
        )
        self.assertEqual(
            normalize_quick_output_format_label("MP3"),
            "MP3 (single file, easiest to share)",
        )

    def test_generate_progress_humanizer(self):
        msg = humanize_generate_progress_desc("Generated chapter 2, segment 5 (Alice)")
        self.assertIn("Chapter 2, segment 5", msg)
        self.assertIn("Speaker Alice", msg)

    def test_quick_mode_error_formatter_includes_retry(self):
        out = format_quick_mode_error(RuntimeError("network timeout"))
        self.assertIn("Quick retry steps", out)
        self.assertIn("Create Audiobook", out)

    def test_tts_engine_factory(self):
        edge = create_tts_engine("edge-tts")
        kokoro = create_tts_engine("kokoro")
        self.assertGreaterEqual(edge.max_concurrent, 1)
        self.assertGreaterEqual(kokoro.max_concurrent, 1)

    def test_pronunciation_dict_case_insensitive_word_boundary(self):
        rules = PronunciationDict({"tom": "TOM"})
        out = rules.apply("Tom met atom and TOM.")
        self.assertEqual(out, "TOM met atom and TOM.")


if __name__ == "__main__":
    unittest.main()
