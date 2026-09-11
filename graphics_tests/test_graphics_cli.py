"""Output preflight tests: command failure must not partially change sidecars."""

from contextlib import redirect_stderr, redirect_stdout
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import graphics_tool


COMPILED = {"ass": "new ass", "srt": "new srt", "duration": 8.0,
            "overlay_count": 1, "caption_count": 1}


class CliOutputTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(prefix="videoai_cli_test_")
        self.directory = Path(self.folder.name)
        self.addCleanup(self.folder.cleanup)
        self.config = self.directory / "config.json"
        self.config.write_text(json.dumps({"duration": 8}), encoding="utf-8")

    def run_cli(self, args):
        stderr = io.StringIO()
        with redirect_stderr(stderr), redirect_stdout(io.StringIO()), \
                patch("videoai_graphics.compiler.compile_graphics", return_value=COMPILED):
            result = graphics_tool.main(args)
        return result, stderr.getvalue()

    def test_existing_srt_blocks_compile_before_ass_is_created(self):
        ass = self.directory / "output.ass"
        srt = self.directory / "output.srt"
        srt.write_text("original srt", encoding="utf-8")
        result, error = self.run_cli(["compile", "--config", str(self.config), "--output", str(ass), "--srt", str(srt)])
        self.assertEqual(result, 1)
        self.assertIn("--overwrite", error)
        self.assertFalse(ass.exists())
        self.assertEqual(srt.read_text(encoding="utf-8"), "original srt")

    def test_duplicate_ass_and_srt_output_rejected_without_writes(self):
        target = self.directory / "output.ass"
        result, error = self.run_cli(["compile", "--config", str(self.config), "--output", str(target), "--srt", str(target)])
        self.assertEqual(result, 1)
        self.assertIn("Duplicate", error)
        self.assertFalse(target.exists())

    def test_config_cannot_be_an_output_even_with_overwrite(self):
        original = self.config.read_bytes()
        ass = self.directory / "output.ass"
        result, error = self.run_cli(["compile", "--config", str(self.config), "--output", str(ass),
                                      "--srt", str(self.config), "--overwrite"])
        self.assertEqual(result, 1)
        self.assertIn("input file", error)
        self.assertFalse(ass.exists())
        self.assertEqual(self.config.read_bytes(), original)

    def test_input_hard_link_alias_is_protected(self):
        alias = self.directory / "config-alias.ass"
        os.link(self.config, alias)
        original = self.config.read_bytes()
        result, error = self.run_cli(["compile", "--config", str(self.config), "--output", str(alias), "--overwrite"])
        self.assertEqual(result, 1)
        self.assertIn("input file", error)
        self.assertEqual(alias.read_bytes(), original)
        self.assertEqual(self.config.read_bytes(), original)

    def test_render_input_alias_rejected_before_renderer_runs(self):
        source = self.directory / "source.mp4"
        alias = self.directory / "alias.mp4"
        source.write_bytes(b"original input")
        os.link(source, alias)
        with patch("videoai_graphics.renderer.render_video") as render:
            result, error = self.run_cli(["render", "--config", str(self.config), "--input", str(source),
                                          "--output", str(alias), "--overwrite"])
        self.assertEqual(result, 1)
        self.assertIn("input file", error)
        render.assert_not_called()

    def test_existing_demo_video_blocks_sidecars_before_any_writes(self):
        directory = self.directory / "demo"
        directory.mkdir()
        video = directory / "gaming_demo.mp4"
        video.write_bytes(b"original video")
        with patch("videoai_graphics.renderer.render_synthetic") as render:
            result, error = self.run_cli(["demo", "--output-dir", str(directory), "--render"])
        self.assertEqual(result, 1)
        self.assertIn("--overwrite", error)
        self.assertEqual(video.read_bytes(), b"original video")
        self.assertEqual(list(directory.iterdir()), [video])
        render.assert_not_called()

    def test_existing_demo_srt_blocks_json_and_ass_creation(self):
        directory = self.directory / "demo"
        directory.mkdir()
        srt = directory / "space_demo.srt"
        srt.write_text("original", encoding="utf-8")
        result, error = self.run_cli(["demo", "--preset", "space", "--output-dir", str(directory)])
        self.assertEqual(result, 1)
        self.assertEqual(list(directory.iterdir()), [srt])
        self.assertEqual(srt.read_text(encoding="utf-8"), "original")

    def test_explicit_compile_overwrite_updates_both_files(self):
        ass = self.directory / "output.ass"
        srt = self.directory / "output.srt"
        ass.write_text("old ass", encoding="utf-8")
        srt.write_text("old srt", encoding="utf-8")
        result, error = self.run_cli(["compile", "--config", str(self.config), "--output", str(ass),
                                      "--srt", str(srt), "--overwrite"])
        self.assertEqual((result, error), (0, ""))
        self.assertEqual(ass.read_text(encoding="utf-8"), "new ass")
        self.assertEqual(srt.read_text(encoding="utf-8"), "new srt")

    def test_write_helper_does_not_overwrite_by_default(self):
        target = self.directory / "existing.txt"
        target.write_text("original", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "--overwrite"):
            graphics_tool._write_text(target, "replacement")
        self.assertEqual(target.read_text(encoding="utf-8"), "original")

    def test_output_parent_collision_rejected_before_directory_creation(self):
        first = self.directory / "new-folder" / "output.ass"
        second = first / "output.srt"
        with self.assertRaisesRegex(ValueError, "output directory"):
            graphics_tool._preflight_outputs([first, second])
        self.assertFalse(first.parent.exists())

    def test_demo_captions_do_not_include_unsupported_enabled_flag(self):
        self.assertNotIn("enabled", graphics_tool.demo_config("gaming")["captions"])

    def test_every_demo_preset_declares_epidemic_as_required_provider(self):
        for preset in graphics_tool.PRESETS:
            self.assertEqual(graphics_tool.demo_config(preset)["audio"], {"provider": "epidemic"})

    def test_render_provider_failure_returns_nonzero_without_output(self):
        source = self.directory / "source.mp4"
        source.write_bytes(b"source")
        output = self.directory / "output.mp4"
        with patch("videoai_graphics.renderer.render_video", side_effect=RuntimeError("Epidemic authentication failed")):
            result, error = self.run_cli(["render", "--config", str(self.config), "--input", str(source),
                                          "--output", str(output)])
        self.assertEqual(result, 1)
        self.assertIn("Epidemic authentication failed", error)
        self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
