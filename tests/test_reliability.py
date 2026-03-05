import tempfile
import unittest
from pathlib import Path
import wave
import contextlib

from audiobook_creator_v7 import AudioCache, build_atempo_filter, load_manifest, save_manifest


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


if __name__ == "__main__":
    unittest.main()
