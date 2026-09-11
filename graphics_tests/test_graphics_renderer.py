"""Regression tests for mandatory Epidemic mixing and safe FFmpeg execution."""

import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from videoai_graphics import renderer


COMPILED = {"ass": "[Script Info]\n", "srt": "", "duration": 8.0,
            "overlay_count": 1, "caption_count": 1}
MEDIA = {"width": 1280, "height": 720, "duration": 8.0, "audio_count": 2}
MANIFEST = {"provider": "epidemic", "api": "official_mcp", "fetched_at": "2026-09-11T00:00:00Z",
            "music": {"id": "music-test-id", "title": "Fixture music", "query": "test music", "gain_db": -24},
            "sfx": [{"id": "sfx-test-id", "title": "Fixture SFX", "query": "test transition", "gain_db": -14,
                     "start": 1.25, "duration": 0.8}]}
RENDERED = {**MEDIA, "audio_manifest": MANIFEST}


class RendererTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(prefix="videoai_renderer_test_")
        self.directory = Path(self.folder.name)
        self.addCleanup(self.folder.cleanup)
        self.music = self.directory / "music fixture.mp3"
        self.effect = self.directory / "effect fixture.mp3"
        self.music.write_bytes(b"mock provider music")
        self.effect.write_bytes(b"mock provider effect")
        self.plan = {"music": {**MANIFEST["music"], "path": str(self.music)},
                     "sfx": [{**MANIFEST["sfx"][0], "path": str(self.effect)}], "manifest": MANIFEST}
        provider_patch = patch.object(renderer, "prepare_audio", return_value=self.plan)
        self.provider = provider_patch.start()
        self.addCleanup(provider_patch.stop)

    def render(self, target, *, encoder="cpu", overwrite=False, fonts_dir=None):
        return renderer._render(COMPILED, target, ["-noautorotate", "-i", "A:/clips/source.mp4"],
                                config={"preset": "gaming"}, source_metadata=True, encoder=encoder, fonts_dir=fonts_dir,
                                overwrite=overwrite, ffmpeg="ffmpeg", ffprobe="ffprobe",
                                expected_media=MEDIA, timeout=30)

    def test_safe_filter_paths_audio_mapping_and_atomic_success(self):
        target = self.directory / "output [review] ' version.mp4"
        fonts = self.directory / "fonts 'colon; and [brackets]"
        fonts.mkdir()
        (fonts / "font.ttf").write_bytes(b"placeholder font")
        commands = []

        def fake_run(command, **kwargs):
            commands.append(command)
            self.assertNotEqual(Path(command[-1]), target)
            workspace = kwargs["cwd"]
            self.assertEqual((workspace / "graphics.ass").read_text(encoding="utf-8-sig"), COMPILED["ass"])
            self.assertTrue((workspace / "fonts" / "font_0000.ttf").is_file())
            self.assertFalse(target.exists())
            Path(command[-1]).write_bytes(b"complete rendered video")
            return subprocess.CompletedProcess(command, 0, "", "")

        with patch.object(renderer, "_executable", side_effect=lambda value: value), \
                patch.object(renderer, "_run", side_effect=fake_run), \
                patch.object(renderer, "probe_video", return_value=RENDERED):
            result = self.render(target, fonts_dir=fonts)
        command = commands[0]
        graph = command[command.index("-filter_complex") + 1]
        self.assertIn("[0:v:0]ass=filename=graphics.ass:fontsdir=fonts[vout]", graph)
        self.assertIn("[0:a:0]", graph)
        self.assertIn("[0:a:1]", graph)
        self.assertIn("[source0][ducked0][effects0]amix=inputs=3", graph)
        self.assertIn("[source1][ducked1][effects1]amix=inputs=3", graph)
        self.assertNotIn("[source0][source1]", graph)
        self.assertIn("[musicbed]asplit=2[music0][music1]", graph)
        self.assertIn("[effectsbed]asplit=2[effects0][effects1]", graph)
        self.assertEqual(graph.count("sidechaincompress="), 2)
        self.assertIn("normalize=0", graph)
        self.assertIn("alimiter=limit=0.95:level=false:latency=true", graph)
        self.assertIn("adelay=delays=60000S:all=1", graph)
        self.assertEqual([command[index+1] for index, value in enumerate(command) if value == "-map"],
                         ["[vout]", "[aout0]", "[aout1]"])
        self.assertEqual(command[command.index("-c:a") + 1], "aac")
        self.assertEqual(command[command.index("-b:a") + 1], "192k")
        self.assertEqual(command[command.index("-map_metadata") + 1], "0")
        self.assertEqual(command[command.index("-map_chapters") + 1], "0")
        self.assertNotIn("-shortest", command)
        self.assertEqual(command[command.index("-t") + 1], "8.000000")
        self.assertNotIn("-an", command)
        self.assertIn("-xerror", command)
        self.assertIn(str(self.music), command)
        self.assertIn(str(self.effect), command)
        self.provider.assert_called_once()
        self.assertEqual(target.read_bytes(), b"complete rendered video")
        self.assertEqual(result["encoder"], "cpu")
        self.assertEqual(result["audio_manifest"], MANIFEST)
        self.assertEqual(list(self.directory.glob("*.partial.mp4")), [])

    def test_auto_falls_back_with_reported_cause(self):
        calls = []

        def fake_run(command, **kwargs):
            calls.append(command)
            if "h264_nvenc" in command:
                Path(command[-1]).write_bytes(b"partial failed render")
                return subprocess.CompletedProcess(command, 1, "", "No NVENC capable devices found")
            Path(command[-1]).write_bytes(b"cpu render")
            return subprocess.CompletedProcess(command, 0, "", "")

        with patch.object(renderer, "_executable", side_effect=lambda value: value), \
                patch.object(renderer, "_run", side_effect=fake_run), \
                patch.object(renderer, "probe_video", return_value=RENDERED):
            result = self.render(self.directory / "output.mp4", encoder="auto")
        self.assertEqual(result["encoder"], "cpu")
        self.assertIn("No NVENC", result["fallback_reason"])
        self.assertEqual(len(calls), 2)
        self.assertIn("libx264", calls[1])
        self.provider.assert_called_once()
        for command in calls:
            self.assertIn(str(self.music), command)
            self.assertIn(str(self.effect), command)
            self.assertNotIn("-an", command)
            self.assertIn("-xerror", command)

    def test_failed_validation_preserves_existing_output(self):
        target = self.directory / "output.mp4"
        target.write_bytes(b"original video")

        def fake_run(command, **kwargs):
            Path(command[-1]).write_bytes(b"bad new render")
            return subprocess.CompletedProcess(command, 0, "", "")

        with patch.object(renderer, "_executable", side_effect=lambda value: value), \
                patch.object(renderer, "_run", side_effect=fake_run), \
                patch.object(renderer, "probe_video", return_value={**RENDERED, "audio_count": 1}):
            with self.assertRaisesRegex(renderer.RenderError, "audio streams"):
                self.render(target, overwrite=True)
        self.assertEqual(target.read_bytes(), b"original video")

    def test_missing_provenance_preserves_existing_output(self):
        target = self.directory / "output.mp4"
        target.write_bytes(b"original video")

        def fake_run(command, **kwargs):
            Path(command[-1]).write_bytes(b"render without provenance")
            return subprocess.CompletedProcess(command, 0, "", "")

        with patch.object(renderer, "_executable", side_effect=lambda value: value), \
                patch.object(renderer, "_run", side_effect=fake_run), \
                patch.object(renderer, "probe_video", return_value=MEDIA):
            with self.assertRaisesRegex(renderer.RenderError, "provenance"):
                self.render(target, overwrite=True)
        self.assertEqual(target.read_bytes(), b"original video")

    def test_provider_failure_aborts_both_public_paths_before_encoding(self):
        source = self.directory / "source.mp4"
        source.write_bytes(b"source video")
        self.provider.side_effect = RuntimeError("Epidemic API unavailable")
        for kind in ("source", "synthetic"):
            target = self.directory / f"{kind}-failure.mp4"
            target.write_bytes(b"existing output")
            with self.subTest(kind=kind), \
                    patch.object(renderer, "_executable", side_effect=lambda value: value), \
                    patch.object(renderer, "_run") as encode, \
                    patch.object(renderer, "probe_video", return_value=MEDIA), \
                    patch("videoai_graphics.compiler.compile_graphics", return_value=COMPILED):
                with self.assertRaisesRegex(RuntimeError, "Epidemic API unavailable"):
                    if kind == "source":
                        renderer.render_video({}, source, target, overwrite=True)
                    else:
                        renderer.render_synthetic({}, target, overwrite=True)
                encode.assert_not_called()
            self.assertEqual(target.read_bytes(), b"existing output")
        self.assertEqual(self.provider.call_count, 2)
        self.assertEqual(list(self.directory.glob("*.partial.mp4")), [])

    def test_silent_input_and_synthetic_output_require_epidemic_audio(self):
        source = self.directory / "silent.mp4"
        source.write_bytes(b"silent source video")
        for kind in ("source", "synthetic"):
            calls = []

            def fake_run(command, **kwargs):
                calls.append(command)
                Path(command[-1]).write_bytes(b"video with required Epidemic audio")
                return subprocess.CompletedProcess(command, 0, "", "")

            def fake_probe(path, **kwargs):
                return ({**MEDIA, "audio_count": 0} if Path(path) == source else
                        {**RENDERED, "audio_count": 1})

            with self.subTest(kind=kind), \
                    patch.object(renderer, "_executable", side_effect=lambda value: value), \
                    patch.object(renderer, "_run", side_effect=fake_run), \
                    patch.object(renderer, "probe_video", side_effect=fake_probe), \
                    patch("videoai_graphics.compiler.compile_graphics", return_value=COMPILED):
                target = self.directory / f"{kind}-mixed.mp4"
                config = {"preset": "space", "epidemic": {"required": True}}
                if kind == "source":
                    result = renderer.render_video(config, source, target, encoder="cpu")
                else:
                    result = renderer.render_synthetic(config, target)
            command = calls[0]
            graph = command[command.index("-filter_complex")+1]
            self.assertNotIn("[0:a:", graph)
            self.assertIn("[music0][effects0]amix=inputs=2", graph)
            self.assertIn("[aout0]", command)
            self.assertNotIn("[aout1]", command)
            self.assertNotIn("-an", command)
            self.assertEqual(result["audio_manifest"], MANIFEST)
            self.assertIn("Epidemic", result["audio"])
            self.assertEqual(self.provider.call_args.args[0], config)
            self.assertEqual(self.provider.call_args.args[1], 8.0)
        self.assertEqual(self.provider.call_count, 2)

    def test_missing_music_or_sfx_never_encodes(self):
        for missing in ("music", "sfx"):
            plan = dict(self.plan)
            plan[missing] = None if missing == "music" else []
            self.provider.return_value = plan
            with self.subTest(missing=missing), \
                    patch.object(renderer, "_executable", side_effect=lambda value: value), \
                    patch.object(renderer, "_run") as encode:
                with self.assertRaisesRegex(renderer.RenderError, "requires Epidemic music"):
                    self.render(self.directory / f"missing-{missing}.mp4")
                encode.assert_not_called()

    def test_manifest_omits_urls_credentials_and_local_paths(self):
        plan = {**self.plan, "manifest": {**MANIFEST, "access_token": "SECRET"},
                "music": {**self.plan["music"], "signed_url": "https://host/track?token=SECRET",
                          "query": "mood https://host/path?token=SECRET"}}
        manifest = renderer._safe_audio_manifest(plan)
        serialized = json.dumps(manifest)
        self.assertNotIn("SECRET", serialized)
        self.assertNotIn(str(self.music), serialized)
        self.assertNotIn("https://", serialized)
        self.assertEqual(manifest["music"]["id"], "music-test-id")

    def test_negligible_or_clipped_sound_effects_abort_before_encoding(self):
        for timing in ({"duration": 1e-9}, {"start": 7.99, "duration": 0.8}):
            self.provider.return_value = {**self.plan, "sfx": [{**self.plan["sfx"][0], **timing}]}
            with self.subTest(timing=timing), \
                    patch.object(renderer, "_executable", side_effect=lambda value: value), \
                    patch.object(renderer, "_run") as encode:
                with self.assertRaisesRegex(renderer.RenderError, "at least 0.02 seconds"):
                    self.render(self.directory / "invalid-timing.mp4")
                encode.assert_not_called()
        self.assertEqual(list(self.directory.glob("*.partial.mp4")), [])

    def test_failed_encoder_preserves_existing_output(self):
        target = self.directory / "output.mp4"
        target.write_bytes(b"original video")
        with patch.object(renderer, "_executable", side_effect=lambda value: value), \
                patch.object(renderer, "_run", return_value=subprocess.CompletedProcess([], 1, "", "encoder error")):
            with self.assertRaisesRegex(renderer.RenderError, "encoder error"):
                self.render(target, overwrite=True)
        self.assertEqual(target.read_bytes(), b"original video")

    def test_publication_will_not_overwrite_concurrently_created_file(self):
        staged = self.directory / "staged.mp4"
        target = self.directory / "output.mp4"
        staged.write_bytes(b"new")
        target.write_bytes(b"existing")
        with self.assertRaises(FileExistsError):
            renderer._publish(staged, target, overwrite=False)
        self.assertEqual(target.read_bytes(), b"existing")

    def test_same_source_output_and_unrequested_overwrite_rejected(self):
        source = self.directory / "source.mp4"
        source.write_bytes(b"source")
        with self.assertRaisesRegex(renderer.RenderError, "different file"):
            renderer._destination(source, source=source, overwrite=True)
        with self.assertRaisesRegex(renderer.RenderError, "already exists"):
            renderer._destination(source, source=None, overwrite=False)

    def test_probe_rejects_rotation_and_non_square_pixels(self):
        source = self.directory / "source.mp4"
        source.write_bytes(b"video")
        stream = {"codec_type": "video", "width": 1280, "height": 720, "duration": "8",
                  "sample_aspect_ratio": "1:1"}
        for change, message in [({"side_data_list": [{"rotation": 90}]}, "rotation"),
                                ({"sample_aspect_ratio": "4:3"}, "non-square")]:
            payload = {"streams": [{**stream, **change}], "format": {"duration": "8"}}
            with self.subTest(change=change), \
                    patch.object(renderer, "_executable", side_effect=lambda value: value), \
                    patch.object(renderer, "_run", return_value=subprocess.CompletedProcess([], 0, json.dumps(payload), "")):
                with self.assertRaisesRegex(renderer.RenderError, message):
                    renderer.probe_video(source)

    def test_probe_rejects_pq_and_hlg_hdr_before_rendering(self):
        source = self.directory / "hdr.mp4"
        source.write_bytes(b"video")
        for transfer in ("smpte2084", "arib-std-b67"):
            payload = {"streams": [{"codec_type": "video", "width": 1280, "height": 720,
                                    "duration": "8", "color_transfer": transfer}],
                       "format": {"duration": "8"}}
            with self.subTest(color_transfer=transfer), \
                    patch.object(renderer, "_executable", side_effect=lambda value: value), \
                    patch.object(renderer, "_run", return_value=subprocess.CompletedProcess([], 0, json.dumps(payload), "")):
                with self.assertRaisesRegex(renderer.RenderError, "Normalize it to SDR"):
                    renderer.probe_video(source)

    def test_probe_accepts_sdr_transfer(self):
        source = self.directory / "sdr.mp4"
        source.write_bytes(b"video")
        payload = {"streams": [{"codec_type": "video", "width": 1280, "height": 720,
                                "duration": "8", "color_transfer": "bt709"}],
                   "format": {"duration": "8"}}
        with patch.object(renderer, "_executable", side_effect=lambda value: value), \
                patch.object(renderer, "_run", return_value=subprocess.CompletedProcess([], 0, json.dumps(payload), "")):
            media = renderer.probe_video(source)
        self.assertEqual((media["width"], media["height"], media["duration"]), (1280, 720, 8))

    def test_probe_reads_embedded_provenance_from_mp4_and_mkv_comment(self):
        source = self.directory / "provenance.mp4"
        source.write_bytes(b"video")
        for tag in ("comment", "COMMENT"):
            payload = {"streams": [{"codec_type": "video", "width": 1280, "height": 720, "duration": "8"}],
                       "format": {"duration": "8", "tags": {tag: json.dumps({"videoai_audio": MANIFEST})}}}
            with self.subTest(tag=tag), \
                    patch.object(renderer, "_executable", side_effect=lambda value: value), \
                    patch.object(renderer, "_run", return_value=subprocess.CompletedProcess([], 0, json.dumps(payload), "")):
                media = renderer.probe_video(source)
            self.assertEqual(media["audio_manifest"], MANIFEST)


if __name__ == "__main__":
    unittest.main()
