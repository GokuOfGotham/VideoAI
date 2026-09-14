"""House graphics system: every subject renders both formats, panels stay inside the frame, covers build."""
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from videoai_graphics import broadcast as bc  # noqa: E402


class BroadcastThemeTests(unittest.TestCase):
    def test_every_subject_renders_main_and_short(self):
        with tempfile.TemporaryDirectory() as tmp:
            for subject in bc.SUBJECTS:
                theme = bc.Theme(subject=subject, channel="TEST CHANNEL", series="SERIES", chapters=["ONE", "TWO"])
                card = bc.Card("A VERY LONG KICKER THAT MUST SHRINK TO FIT THE HEADER", "$1.3 TRILLION", ["one", "two", "three"], "credit")
                for kind, size in (("main", (1920, 1080)), ("short", (1080, 1920))):
                    shots = (bc.Shot(kind, 1, card, bc.Source("CBS NEWS", "CBS Mornings", "September 10, 2026", "1920x1080"), True, "SPEAKER NAME"),
                             bc.Shot(kind, 0, card, bc.Source("PBS", "News Hour", "September 10, 2026"), False),
                             bc.Shot(kind, 0, card, None, False, exhibit=bc.Exhibit("TOP", "$1.3 TRILLION", "NOTE", 0.5)),
                             bc.Shot(kind, 0, card, None, False))
                    for shot in shots:
                        png, (x, y, w, h) = bc.render_plate(theme, shot, Path(tmp) / f"{subject}_{kind}.png")
                        with Image.open(png) as im:
                            self.assertEqual(im.size, size)
                        self.assertTrue(0 <= x and x + w <= size[0] and 0 <= y and y + h <= size[1])

    def test_caption_plumbing_and_contrast(self):
        theme = bc.Theme(subject="science")
        self.assertIn("PlayResX: 1920", bc.ass_header("main", theme))
        self.assertIn("PlayResX: 1080", bc.ass_header("short", theme))
        self.assertTrue(bc.caption_tag("main").startswith("{\\an4\\pos("))
        self.assertIn("Dialogue: 5,", bc.progress_bar("main", theme, 0.0, 2.0, lambda t: "0:00:00.00"))
        self.assertEqual(bc.on("#F59E0B"), bc.INK)
        self.assertEqual(bc.on("#1B4ED8"), bc.WHITE)

    def test_cover_both_orientations(self):
        with tempfile.TemporaryDirectory() as tmp:
            frame = Image.new("RGB", (1920, 1080), "#334455")
            theme = bc.Theme(subject="gaming", channel="TEST")
            a = bc.cover(theme, frame, "12 SEC", "ROUTE SAVING", "THE\nTRICK", "TAGS", "NOTE", Path(tmp) / "a.jpg")
            b = bc.cover(theme, frame, "12 SEC", "ROUTE SAVING", "THE TRICK", "TAGS", "", Path(tmp) / "b.jpg", vertical=True)
            with Image.open(a) as ia, Image.open(b) as ib:
                self.assertEqual(ia.size, (1280, 720))
                self.assertEqual(ib.size, (1080, 1920))


if __name__ == "__main__":
    unittest.main()
