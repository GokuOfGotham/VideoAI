import math
import re
import unittest

from videoai_graphics.captions import build_captions


def words(*tokens, start=0.0, step=0.4):
    return [{"word": token, "start": start + index * step, "end": start + index * step + step * 0.75} for index, token in enumerate(tokens)]


class CaptionTests(unittest.TestCase):
    def test_srt_millisecond_rollover_and_ass_centiseconds(self):
        result = build_captions([{"word": "Rollover", "start": 59.9996, "end": 60.2004}], 1920, 1080, "space")
        self.assertIn("00:01:00,000 --> 00:01:00,320", result["srt"])
        self.assertEqual(result["events"][0]["start"], 60.0)
        self.assertEqual(result["events"][0]["end"], 60.32)

    def test_ass_hostile_text_cannot_create_overrides_or_line_breaks(self):
        payload = r"{\p1}m 0 0 l 100 100{\p0}\N" + "\r\nunsafe\x00"
        result = build_captions(words(payload), 1920, 1080, options={"max_chars": 120})
        text = result["events"][0]["text"]
        self.assertNotIn(r"{\p1}", text)
        self.assertNotIn(r"\p0", text)
        self.assertIn("\uff5b\uff3cp1\uff5d", text)
        self.assertNotIn("\r", text)
        self.assertNotIn("\x00", text)
        self.assertNotIn("\nunsafe", result["srt"])

    def test_pause_and_punctuation_break_phrases_without_long_hold(self):
        source = words("Hello,", "world", "again")
        source.extend(words("Much", "later.", start=4.0))
        result = build_captions(source, 1080, 1920)
        self.assertEqual([group["text"] for group in result["groups"]], ["Hello,", "world again", "Much later."])
        self.assertLess(result["groups"][1]["end"], 1.3)
        self.assertEqual(result["groups"][2]["start"], 4.0)

    def test_wrapping_has_at_most_two_lines_and_keeps_every_word(self):
        source = words("one", "two", "three", "four", "five", "six", "seven", "eight")
        result = build_captions(source, 720, 1280, "political", {"max_chars": 10, "words_per_caption": 12})
        self.assertEqual(" ".join(group["text"] for group in result["groups"]), "one two three four five six seven eight")
        self.assertTrue(any(r"\N" in event["text"] for event in result["events"]))
        for event in result["events"]:
            self.assertLessEqual(event["text"].count(r"\N"), 1)
        for block in result["srt"].strip().split("\n\n"):
            for line in block.splitlines()[2:]:
                self.assertLessEqual(len(line), 10)

    def test_wide_glyphs_trigger_pixel_aware_wrapping(self):
        result = build_captions(words("WWWWWW", "WWWWWW", "WWWWWW"), 360, 640, "space", {"font_size": 50, "max_chars": 60})
        self.assertEqual(len(result["groups"]), 2)
        self.assertIn(r"\N", result["events"][0]["text"])

    def test_highlight_is_gapless_and_updates_active_word(self):
        result = build_captions(words("Red", "green", "blue"), 1920, 1080, options={"active_color": "#12AB34"})
        events = result["events"]
        self.assertEqual(len(events), 3)
        for index, token in enumerate(("Red", "green", "blue")):
            self.assertIn(r"{\1c&H34AB12&}" + token, events[index]["text"])
            if index:
                self.assertEqual(events[index - 1]["end"], events[index]["start"])
        self.assertIn(r"\fnArial", events[0]["text"])
        self.assertIn(r"\pos(960.0,950.4)", events[0]["text"])

    def test_clean_and_karaoke_have_expected_styles(self):
        clean = build_captions(words("Ready", "now"), 1080, 1920, "political")
        karaoke = build_captions(words("Ready", "now"), 1080, 1920, "reaction", {"style": "karaoke", "position": "center", "y": 0.4, "uppercase": True})
        self.assertEqual(len(clean["events"]), 1)
        self.assertNotIn(r"\kf", clean["events"][0]["text"])
        text = karaoke["events"][0]["text"]
        self.assertIn(r"\an5\pos(540.0,768.0)", text)
        self.assertIn("READY", text)
        durations = [int(value) for value in re.findall(r"\\kf(\d+)", text)]
        self.assertEqual(durations, [40, 42])
        self.assertEqual(sum(durations), round((karaoke["events"][0]["end"] - karaoke["events"][0]["start"]) * 100))

    def test_unsorted_overlaps_and_equal_starts_keep_stable_word_order(self):
        source = [
            {"word": "third", "start": 1.0, "end": 1.8},
            {"word": "first", "start": 0.0, "end": 1.5},
            {"word": "second", "start": 0.0, "end": 1.2},
        ]
        result = build_captions(source, 1920, 1080)
        self.assertEqual(result["groups"][0]["text"], "first second third")
        self.assertTrue(all(event["end"] > event["start"] for event in result["events"]))
        self.assertTrue(all(a["end"] <= b["start"] for a, b in zip(result["events"], result["events"][1:])))
        self.assertEqual(source[0]["word"], "third")

    def test_invalid_times_rejected(self):
        for start, end in [(-1, 2), (0, 0), (2, 1), (math.nan, 2), (0, math.inf), (True, 2), ("0", 1)]:
            with self.subTest(start=start, end=end), self.assertRaises(ValueError):
                build_captions([{"word": "test", "start": start, "end": end}], 1920, 1080)

    def test_equal_start_punctuation_does_not_drop_a_word(self):
        result = build_captions([
            {"word": "First.", "start": 0, "end": 0.4},
            {"word": "Second", "start": 0, "end": 0.4},
        ], 1920, 1080)
        self.assertEqual(result["groups"][0]["text"], "First. Second")

    def test_invalid_preset_raises_value_error(self):
        with self.assertRaises(ValueError):
            build_captions(words("test"), 1920, 1080, preset=[])

    def test_video_duration_caps_ass_srt_and_group_tail_holds(self):
        result = build_captions([
            {"word": "Last", "start": 2.0, "end": 2.4},
            {"word": "words", "start": 2.5, "end": 3.0},
        ], 1920, 1080, duration=3.0)
        self.assertEqual(result["groups"][-1]["end"], 3.0)
        self.assertEqual(result["events"][-1]["end"], 3.0)
        self.assertIn("--> 00:00:03,000", result["srt"])

    def test_video_duration_rounding_cannot_extend_exports(self):
        result = build_captions([
            {"word": "End", "start": 1.0, "end": 1.2346},
        ], 1920, 1080, duration=1.2346)
        self.assertEqual(result["groups"][-1]["end"], 1.2346)
        self.assertEqual(result["events"][-1]["end"], 1.23)
        self.assertIn("--> 00:00:01,234", result["srt"])

    def test_out_of_video_words_rejected_before_overlap_clipping(self):
        for source in [
            [{"word": "after", "start": 3.0, "end": 3.5}],
            [{"word": "overrun", "start": 2.0, "end": 3.2}],
            [{"word": "overlap", "start": 0.0, "end": 4.0}, {"word": "inside", "start": 1.0, "end": 2.0}],
        ]:
            with self.subTest(source=source), self.assertRaises(ValueError):
                build_captions(source, 1920, 1080, duration=3.0)

    def test_duration_validation_and_tiny_end_tolerance(self):
        for duration in (0, -1, math.inf, math.nan, True, "3"):
            with self.subTest(duration=duration), self.assertRaises(ValueError):
                build_captions(words("test"), 1920, 1080, duration=duration)
        result = build_captions([
            {"word": "safe", "start": 0.0, "end": 1.0000005},
        ], 1920, 1080, duration=1.0)
        self.assertEqual(result["events"][-1]["end"], 1.0)

    def test_unsafe_or_invalid_options_rejected(self):
        invalid = [
            {"font_name": r"Arial\bord0"}, {"font_name": "Arial,1"},
            {"active_color": "red"}, {"color": "#FFFFFF}bad{"},
            {"font_size": math.inf}, {"font_size": 0},
            {"words_per_caption": 1.5}, {"max_chars": 0},
            {"style": "anything"}, {"position": "left"},
            {"y": 2}, {"uppercase": "yes"}, {"unknown": True},
        ]
        for options in invalid:
            with self.subTest(options=options), self.assertRaises(ValueError):
                build_captions(words("test"), 1920, 1080, options=options)

    def test_empty_input_returns_empty_outputs(self):
        self.assertEqual(build_captions([], 1920, 1080), {"events": [], "srt": "", "groups": []})


if __name__ == "__main__":
    unittest.main()
