"""Ingest, visual, audio and colour tools on synthetic FFmpeg media; providers are mocked."""

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from videoai_editroom import EditRoomError, audio, color, ingest, visual

HAVE_FFMPEG = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def _ffmpeg(*args):
    subprocess.run(["ffmpeg", "-hide_banner", "-v", "error", "-y", *args], check=True)


@unittest.skipUnless(HAVE_FFMPEG, "FFmpeg is required for the media tests")
class SyntheticMediaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="editroom_"))
        cls.ref = cls.tmp / "ref.mp4"
        # 6 s test pattern with a 440 Hz tone that goes silent from 2.0 to 3.5 s
        _ffmpeg("-f", "lavfi", "-i", "testsrc2=size=320x180:rate=30:duration=6",
                "-f", "lavfi", "-i", "sine=frequency=440:duration=6",
                "-af", "volume='if(between(t,2,3.5),0.001,1)':eval=frame",
                "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", str(cls.ref))
        cls.delayed = cls.tmp / "delayed.m4a"
        _ffmpeg("-i", str(cls.ref), "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono:d=1.5",
                "-filter_complex", "[1:a][0:a]concat=n=2:v=0:a=1[a]", "-map", "[a]", "-c:a", "aac", str(cls.delayed))
        cls.music = cls.tmp / "music.m4a"
        _ffmpeg("-f", "lavfi", "-i", "sine=frequency=220:duration=6", "-c:a", "aac", str(cls.music))
        cls.warm = cls.tmp / "warm.mp4"
        _ffmpeg("-f", "lavfi", "-i", "testsrc2=size=320x180:rate=30:duration=2",
                "-vf", "colorbalance=rs=0.3:bs=-0.2,eq=brightness=0.1", "-c:v", "libx264", "-preset", "ultrafast",
                "-pix_fmt", "yuv420p", str(cls.warm))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    # --- ingest ---

    def test_sync_finds_the_inserted_delay(self):
        report = ingest.sync_multicam(self.ref, [self.delayed])
        angle = report["angles"][0]
        self.assertAlmostEqual(angle["offset_seconds"], 1.5, delta=0.05)
        self.assertTrue(angle["reliable"])
        self.assertEqual(angle["kind"], "audio")
        self.assertEqual(angle["offset_frames"], 45)

    def test_silence_detection_and_keep_ranges(self):
        transcript = {"words": [{"word": "um", "start": 0.5, "end": 0.7}, {"word": "go", "start": 0.8, "end": 1.0}],
                      "segments": [{"start": 0.5, "end": 1.0, "text": "um go for launch now"},
                                   {"start": 4.0, "end": 5.0, "text": "go for launch now please"}]}
        report = ingest.detect_silence(self.ref, noise_db=-50, min_duration=0.5, transcript=transcript)
        self.assertEqual(len(report["silences"]), 1)
        silence = report["silences"][0]
        self.assertAlmostEqual(silence["start"], 2.0, delta=0.1)
        self.assertAlmostEqual(silence["end"], 3.5, delta=0.1)
        self.assertEqual([f["word"] for f in report["fillers"]], ["um"])
        self.assertEqual(len(report["retakes"]), 1)
        ranges = ingest.keep_ranges(report["silences"], report["duration"])
        self.assertEqual(len(ranges), 2)
        self.assertEqual(ranges[0][0], 0.0)
        self.assertEqual(ranges[-1][1], 6.0)

    def test_proxies_are_smaller_and_skip_existing(self):
        report = ingest.generate_proxies([self.ref], self.tmp / "proxies", height=90)
        proxy = Path(report["proxies"][0]["proxy"])
        self.assertTrue(proxy.exists())
        info = json.loads(subprocess.run(["ffprobe", "-v", "error", "-print_format", "json", "-show_streams", str(proxy)],
                                         capture_output=True, text=True).stdout)
        video = next(s for s in info["streams"] if s["codec_type"] == "video")
        self.assertEqual(video["height"], 90)
        again = ingest.generate_proxies([self.ref], self.tmp / "proxies", height=90)
        self.assertEqual(again["proxies"][0]["skipped"], "exists")

    def test_transcribe_uses_supplied_diarizer_and_marks_heuristics(self):
        words = [{"word": "Hello", "start": 0.1, "end": 0.4}, {"word": "there.", "start": 0.5, "end": 0.9},
                 {"word": "Hi.", "start": 3.0, "end": 3.3}]
        with patch.object(ingest, "_whisper_words", return_value=("Hello there. Hi.", [dict(w) for w in words], "cpu")):
            report = ingest.transcribe_media(self.ref, diarizer=lambda p, ws: ["A", "A", "B"])
            self.assertEqual(report["speaker_method"], "diarizer")
            self.assertEqual([s["speaker"] for s in report["segments"]], ["A", "B"])
            self.assertEqual(report["segments"][1]["timecode"], "00:00:03:00")
            report = ingest.transcribe_media(self.ref)
            self.assertEqual(report["speaker_method"], "heuristic-turns")
            self.assertIn("not identification", report["speaker_note"])
            with self.assertRaises(EditRoomError):
                ingest.transcribe_media(self.ref, diarizer=lambda p, ws: ["A"])

    # --- visual ---

    def test_reframe_crops_to_native_vertical(self):
        out = self.tmp / "vertical.mp4"
        report = visual.auto_reframe(self.ref, out, detector="motion", sample_fps=2)
        self.assertEqual(report["output_size"], "100x180")
        self.assertTrue(out.exists())
        self.assertEqual(report["detector"], "motion")
        with self.assertRaises(EditRoomError):
            visual.auto_reframe(self.ref, out, aspect="16:9")

    def test_captions_break_on_speaker_and_sentence(self):
        words = [{"word": "The", "start": 0.2, "end": 0.4, "speaker": "S1"},
                 {"word": "end.", "start": 0.4, "end": 0.8, "speaker": "S1"},
                 {"word": "No", "start": 1.0, "end": 1.2, "speaker": "S1"},
                 {"word": "way", "start": 1.2, "end": 1.5, "speaker": "S2"}]
        report = visual.generate_captions(words, output_base=self.tmp / "caps", kind="short", speaker_labels=True)
        self.assertEqual(report["cue_count"], 3)
        srt = Path(report["srt"]).read_text(encoding="utf-8")
        self.assertIn("[S2] way", srt)
        ass = Path(report["ass"]).read_text(encoding="utf-8")
        self.assertIn("Style: Narr", ass)
        self.assertEqual(ass.count("Dialogue:"), 3)
        with self.assertRaises(EditRoomError):
            visual.generate_captions(words, output_base=self.tmp / "caps2", duration=1.0)

    def test_broll_uses_bin_then_mocked_youtube(self):
        bin_dir = self.tmp / "bin"
        bin_dir.mkdir(exist_ok=True)
        shutil.copy(self.warm, bin_dir / "rocket_launch_pad.mp4")
        report = visual.search_visual_broll("rocket launch", providers=["bin"], bin_dir=bin_dir)
        self.assertEqual(report["results"][0]["provider"], "bin")

        class Clip:
            path, title, channel, webpage_url, license = "yt.mp4", "Launch", "NASA TV", "https://y/t", "Creative Commons"
            source_start, source_end, requires_attribution = 1.0, 6.0, True

        with patch.dict("sys.modules", {"youtube_broll": type("M", (), {"fetch_broll_clip": staticmethod(lambda *a, **k: Clip())})}):
            report = visual.search_visual_broll("", transcript_text="Engineers examined the rocket valve failure",
                                                providers=["youtube"])
        self.assertEqual(report["query"], "Engineers examined rocket valve failure")
        self.assertIn("NASA TV", report["results"][0]["attribution"])

    # --- audio ---

    def test_clean_dialogue_levels_and_keeps_video_only_in_video_containers(self):
        wav = audio.clean_dialogue(self.ref, self.tmp / "clean.wav", strength="light")
        self.assertTrue(Path(wav["output"]).exists())
        self.assertAlmostEqual(wav["after"]["integrated_lufs"], -16.0, delta=3.0)
        mp4 = audio.clean_dialogue(self.ref, self.tmp / "clean.mp4", strength="heavy", target_lufs=None)
        info = json.loads(subprocess.run(["ffprobe", "-v", "error", "-print_format", "json", "-show_streams", mp4["output"]],
                                         capture_output=True, text=True).stdout)
        self.assertEqual(sorted(s["codec_type"] for s in info["streams"]), ["audio", "video"])

    def test_ducking_lifts_music_in_the_gap(self):
        keys = audio.ducking_keyframes(self.ref, duck_db=-12, threshold_db=-40)
        self.assertEqual(keys[0]["gain_db"], -12)
        rises = [k for k in keys if k["gain_db"] == 0.0]
        self.assertTrue(any(2.0 < k["time"] < 3.2 for k in rises))
        stem = self.tmp / "stem.wav"
        report = audio.apply_audio_ducking(self.music, self.ref, stem, duck_db=-12, music_gain_db=0, mix=False)
        self.assertEqual(report["speech_regions"], 1)

        def rms(start, length):
            log = subprocess.run(["ffmpeg", "-hide_banner", "-ss", str(start), "-t", str(length), "-i", str(stem),
                                  "-af", "astats=measure_overall=RMS_level:measure_perchannel=none", "-f", "null", "-"],
                                 capture_output=True, text=True).stderr
            return float([l for l in log.splitlines() if "RMS level dB" in l][-1].split(":")[-1])
        self.assertGreater(rms(2.5, 0.6) - rms(0.5, 1.0), 8.0)

    def test_adr_refuses_to_stretch_and_splices_when_it_fits(self):
        take = self.tmp / "take.wav"
        _ffmpeg("-f", "lavfi", "-i", "sine=frequency=880:duration=0.8", "-c:a", "pcm_s16le", str(take))

        def fake_synth(text, dest, preset=None):
            shutil.copy(take, dest)
            return Path(dest)

        fake_module = type("M", (), {"synthesize": staticmethod(fake_synth)})
        with patch.dict("sys.modules", {"narration_tools": fake_module}):
            short = audio.generate_adr(self.ref, self.tmp / "adr.wav", text="x", start=1.0, end=1.5)
            self.assertEqual(short["status"], "rewrite_needed")
            done = audio.generate_adr(self.ref, self.tmp / "adr.wav", text="x", start=1.0, end=2.0)
        self.assertEqual(done["status"], "replaced")
        self.assertAlmostEqual(ingest.media_duration(done["output"]), 6.0, delta=0.1)
        self.assertIn("not a clone", done["note"])

    # --- colour ---

    def test_match_color_reduces_lab_distance_and_writes_cube(self):
        report = color.match_color(self.ref, self.warm, self.tmp / "matched.mp4", samples=6, size=17)
        self.assertLess(report["mean_distance_after"], report["mean_distance_before"])
        cube = Path(report["cube"]).read_text(encoding="utf-8")
        self.assertIn("LUT_3D_SIZE 17", cube)
        self.assertEqual(len([l for l in cube.splitlines() if l and l[0].isdigit()]), 17 ** 3)

    def test_apply_builtin_looks_and_user_lut(self):
        for look in ("rec709", "teal_orange", "slog3_to_rec709"):
            report = color.apply_lut(self.warm, self.tmp / f"{look}.mp4", lut=look, size=9)
            self.assertTrue(Path(report["output"]).exists())
        identity = color.look_lut("rec709", size=5)
        self.assertEqual(identity.shape, (125, 3))
        with self.assertRaises(EditRoomError):
            color.apply_lut(self.warm, self.tmp / "bad.mp4", lut="not_a_look")
        with self.assertRaises(EditRoomError):
            color.look_lut("nope")


if __name__ == "__main__":
    unittest.main()
