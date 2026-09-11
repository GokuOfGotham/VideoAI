import unittest

from videoai_graphics.compiler import compile_graphics


class GraphicsCompilerTests(unittest.TestCase):
    def test_every_category_and_overlay_supports_both_aspects(self):
        for preset in ("political", "space", "gaming", "reaction"):
            for width, height in ((1080, 1920), (1280, 720)):
                for kind in ("lower_third", "title_card", "callout", "badge", "ticker", "progress_bar", "reaction_frame"):
                    with self.subTest(preset=preset, size=(width,height), kind=kind):
                        result = compile_graphics({"preset":preset,"duration":8,"overlays":[
                            {"type":kind,"start":0,"end":8,"title":"Scene context","subtitle":"Supporting detail"}
                        ]},width,height)
                        self.assertIn(f"PlayResX: {width}",result["ass"])
                        self.assertIn("Dialogue:",result["ass"])
                        self.assertEqual(result["overlay_count"],1)

    def test_text_cannot_inject_ass_commands(self):
        result=compile_graphics({"overlays":[{"type":"badge","start":0,"end":2,
                                  "title":r"{\pos(0,0)} Fake\Nline"}]},1280,720)
        self.assertNotIn(r"{\pos(0,0)}",result["ass"])
        self.assertNotIn(r"Fake\Nline",result["ass"])

    def test_invalid_timelines_are_rejected(self):
        for start,end in ((-1,2),(2,1),(0,float("nan")),(0,10)):
            with self.subTest(start=start,end=end), self.assertRaises(ValueError):
                compile_graphics({"duration":8,"overlays":[{"type":"badge","start":start,"end":end,"title":"Cue"}]},1280,720)

    def test_minute_rollover_is_valid_ass(self):
        result=compile_graphics({"duration":61,"overlays":[{"type":"badge","start":59.999,"end":61,"title":"Cue"}]},1280,720)
        self.assertIn("0:01:00.00",result["ass"])
        self.assertNotIn(":60.",result["ass"])

    def test_overlong_text_fails_instead_of_clipping(self):
        with self.assertRaises(ValueError):
            compile_graphics({"overlays":[{"type":"lower_third","start":0,"end":2,"title":"W"*250}]},1080,1920)

    def test_source_duration_controls_limits(self):
        result=compile_graphics({"duration":3,"overlays":[{"type":"badge","start":0,"end":7,"title":"Cue"}]},1280,720,duration=10)
        self.assertEqual(result["duration"],10)

    def test_invalid_font_and_color_are_rejected(self):
        with self.assertRaises(ValueError):
            compile_graphics({"font_name":r"Arial\pos(1,1)"},1280,720)
        with self.assertRaises(ValueError):
            compile_graphics({"overlays":[{"type":"badge","start":0,"end":2,"title":"Cue","color":"red"}]},1280,720)

    def test_off_canvas_badge_and_late_cue_rejected(self):
        with self.assertRaises(ValueError):
            compile_graphics({"overlays":[{"type":"badge","start":0,"end":2,"title":"Cue","y":.97}]},1920,1080)
        with self.assertRaises(ValueError):
            compile_graphics({"duration":1,"overlays":[{"type":"badge","start":1.02,"end":1.04,"title":"Cue"}]},1280,720)

    def test_final_subtitle_does_not_extend_past_video(self):
        result=compile_graphics({"duration":1,"words":[{"word":"Hello","start":.5,"end":1}]},1280,720)
        self.assertIn("00:00:01,000",result["srt"])
        self.assertNotIn("00:00:01,120",result["srt"])


if __name__ == "__main__":
    unittest.main()
