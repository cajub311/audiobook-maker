import tempfile
import unittest
from pathlib import Path
import wave
import contextlib
import asyncio

from audiobook_creator_v7 import (
    AudioCache,
    build_atempo_filter,
    choose_resume_project_id,
    load_manifest,
    manifest_has_generation_errors,
    save_manifest,
    stage_generate,
    validate_safe_http_url,
)


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


if __name__ == "__main__":
    unittest.main()
