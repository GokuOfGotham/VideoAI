"""Offline tests for videoai_director: no network, no media, no API keys."""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from videoai_director import story, excerpts, review  # noqa: E402
from videoai_director.scene_index import scenes_from_cuts, lines_from_words, find  # noqa: E402
from videoai_policy import validate_plan, validate_script, ProductionPolicyError, review_template  # noqa: E402


def good_spine(duration=900.0):
    return {"title_question": "Can Wolverine really beat Omega Red?",
            "thesis": "Yes, twice this year, and neither time could he finish him.",
            "beats": [{"role": "hook", "at": 0, "text": "Omega Red's own line with original audio"},
                      {"role": "claim", "at": 14, "text": "Yes. Twice. Neither time dead."},
                      {"role": "evidence", "at": 40, "text": "X-Men #4, the coils, the drain"},
                      {"role": "evidence", "at": 95, "text": "The stolen synthesizer"},
                      {"role": "evidence", "at": 150, "text": "Skull by sunrise excerpt"},
                      {"role": "evidence", "at": 205, "text": "Round one excerpts"},
                      {"role": "evidence", "at": 260, "text": "Health bar barely moves"},
                      {"role": "turn", "at": 330, "text": "In a straight drain, Wolverine loses"},
                      {"role": "evidence", "at": 380, "text": "The Voice; the Reavers"},
                      {"role": "rehook", "at": 400, "text": "Round two moves outside"},
                      {"role": "evidence", "at": 440, "text": "No better than the rest of the world"},
                      {"role": "evidence", "at": 500, "text": "You are nothing"},
                      {"role": "evidence", "at": 560, "text": "The rematch"},
                      {"role": "open_loop", "at": 590, "loop_id": "sample", "text": "Essex wants a sample"},
                      {"role": "rehook", "at": 642, "text": "Now the other answer: X-Men '97"},
                      {"role": "evidence", "at": 690, "text": "Morph, the tank"},
                      {"role": "evidence", "at": 740, "text": "Omega Red wakes"},
                      {"role": "evidence", "at": 790, "text": "Sixteen seconds"},
                      {"role": "payoff", "at": 853, "text": "Same fight, two answers: Wolverine beats Omega Red both times"},
                      {"role": "close_loop", "at": 890, "loop_id": "sample", "text": "That's why Essex wants a sample"},
                      {"role": "button", "at": 895, "text": "Watch what he does with it"}],
            "chapters": [{"title": "OMEGA MEANS THE END", "start": 0, "kind": "claim"},
                         {"title": "WHO IS OMEGA RED", "start": 38, "kind": "question"},
                         {"title": "THE DRAIN", "start": 304, "kind": "claim"}]}


class StoryTests(unittest.TestCase):
    def test_good_spine_has_no_errors(self):
        r = story.validate_spine(good_spine(), 900.0)
        self.assertEqual(r["errors"], [], r)

    def test_late_answer_is_an_error(self):
        s = good_spine(); [b for b in s["beats"] if b["role"] == "claim"][0]["at"] = 40
        r = story.validate_spine(s, 900.0)
        self.assertTrue(any("answer must be stated" in e for e in r["errors"]), r)

    def test_missing_turn_and_button(self):
        s = good_spine(); s["beats"] = [b for b in s["beats"] if b["role"] not in ("turn", "button")]
        r = story.validate_spine(s, 900.0)
        self.assertTrue(any("no turn" in e for e in r["errors"]))
        self.assertTrue(any("no button" in e for e in r["errors"]))

    def test_unclosed_loop_is_an_error(self):
        s = good_spine(); s["beats"] = [b for b in s["beats"] if b["role"] != "close_loop"]
        r = story.validate_spine(s, 900.0)
        self.assertTrue(any("never closed" in e for e in r["errors"]))

    def test_rehook_gap_warns_on_long_form(self):
        s = good_spine(); s["beats"] = [b for b in s["beats"] if b["role"] not in ("rehook", "open_loop", "close_loop")]
        r = story.validate_spine(s, 900.0)
        self.assertTrue(any("without a new question" in w for w in r["warnings"]), r)

    def test_ending_must_echo_title(self):
        s = good_spine()
        for b in s["beats"]:
            if b["role"] in ("payoff", "button"):
                b["text"] = "and that is all for today"
        r = story.validate_spine(s, 900.0)
        self.assertTrue(any("title question" in w for w in r["warnings"]), r)

    def test_script_repeats(self):
        script = "carbonadium doesn't care about claws. " * 3 + "It is fine."
        ws = story.script_warnings(script)
        self.assertTrue(any("repeated 3" in w for w in ws), ws)

    def test_template_fails_until_filled(self):
        r = story.validate_spine(story.template(600), 600.0)
        self.assertTrue(r["errors"])


class PolicyIntegrationTests(unittest.TestCase):
    def plan(self, spine=None, fmt="long"):
        rv = review_template("lore", fmt)
        rv.update(hook="Omega Red's line with original audio at second zero.", first_payoff_seconds=14,
                  first_payoff="The narration answers the title: yes, twice, neither time dead.",
                  pacing_review="Narrated essay; excerpts cut on word boundaries; repeated whip cycles removed.")
        p = {"title": "Can Wolverine beat Omega Red?", "production_review": rv, "narration_script": "Yes. He did it twice.", "duration": 900}
        if spine is not None:
            p["story_spine"] = spine
        return p

    def test_plan_with_valid_spine_passes_and_reports(self):
        res = validate_script(self.plan(good_spine()), duration=900)
        self.assertEqual(res["story"]["errors"], [])

    def test_plan_with_broken_spine_fails(self):
        s = good_spine(); s["beats"] = [b for b in s["beats"] if b["role"] != "button"]
        with self.assertRaises(ProductionPolicyError):
            validate_script(self.plan(s), duration=900)

    def test_long_plan_without_spine_only_warns(self):
        res = validate_script(self.plan(), duration=900)
        self.assertTrue(res["story"]["warnings"])

    def test_short_plan_without_spine_is_silent(self):
        res = validate_script(self.plan(fmt="short"), duration=50)
        self.assertIsNone(res["story"])


class SceneIndexTests(unittest.TestCase):
    def test_spans_merge_and_split(self):
        spans = scenes_from_cuts([0.1, 5.0, 5.2, 30.0], 40.0, max_shot=10.0)
        self.assertEqual(spans[0], (0.0, 5.0))
        # 5.0-30.0 is 25 s -> three beats; 30-40 -> one
        self.assertEqual(len(spans), 1 + 3 + 1)
        self.assertAlmostEqual(spans[-1][1], 40.0)

    def test_lines_group_on_punctuation_and_gaps(self):
        words = [{"word": "You", "start": 0.0, "end": 0.2}, {"word": "think", "start": 0.2, "end": 0.5}, {"word": "so?", "start": 0.5, "end": 0.8},
                 {"word": "No.", "start": 1.0, "end": 1.3}, {"word": "Later", "start": 5.0, "end": 5.4}, {"word": "words", "start": 5.4, "end": 5.8}]
        lines = lines_from_words(words)
        self.assertEqual([l["text"] for l in lines], ["You think so?", "No.", "Later words"])

    def test_find_ranks_by_meaning(self):
        log = {"scenes": [{"index": 0, "start": 0, "end": 5, "description": "Wide shot of a warehouse", "characters": [], "dialogue": []},
                          {"index": 1, "start": 5, "end": 9, "description": "Close-up of Omega Red, red coils glowing", "characters": ["Omega Red"],
                           "dialogue": [{"start": 6, "end": 8, "text": "Omega, it means the end.", "speaker": "Omega Red"}]}]}
        hits = find(log, "omega red red coils close-up")
        self.assertEqual(hits[0]["index"], 1)


class ExcerptTests(unittest.TestCase):
    def test_candidates_rank_exchange_with_names_first(self):
        log = {"label": "boss", "duration": 100.0, "scenes": [{"index": 0, "start": 0, "end": 30, "energy": "high", "kind": "cutscene", "description": "x"}],
               "lines": [{"start": 10.0, "end": 12.0, "text": "Do you even know why your team rejected me?", "speaker": "Omega Red", "scene": 0,
                          "words": [{"word": "Do", "start": 10.0, "end": 10.2}, {"word": "me?", "start": 11.8, "end": 12.0}]},
                         {"start": 12.3, "end": 13.4, "text": "Cuz you're sick.", "speaker": "Logan", "scene": 0,
                          "words": [{"word": "Cuz", "start": 12.3, "end": 12.5}, {"word": "sick.", "start": 13.1, "end": 13.4}]},
                         {"start": 40.0, "end": 40.4, "text": "No!", "speaker": "", "scene": 0, "words": [{"word": "No!", "start": 40.0, "end": 40.4}]}]}
        rows = excerpts.candidates(log, src="boss", brief=["Team X rejected"])
        self.assertEqual(rows[0]["speaker"], "OMEGA RED / LOGAN")
        self.assertAlmostEqual(rows[0]["a"], 10.0 - excerpts.LEAD, places=2)
        self.assertAlmostEqual(rows[0]["b"], 13.4 + excerpts.TAIL, places=2)
        self.assertEqual(rows[0]["quotes"][0][2], "Omega Red: Do you even know why your team rejected me?")
        self.assertTrue(rows[-1]["text"] == "No!" and rows[-1]["score"] < rows[0]["score"])


class ReviewTests(unittest.TestCase):
    def test_digest_attaches_scene_and_review_uses_injected_call(self):
        plan = {"title": "T", "production_review": {"content_type": "lore", "format": "long"}, "story_spine": good_spine(60.0)}
        for b in plan["story_spine"]["beats"]:
            b["at"] = min(b["at"], 59)
        timeline = {"duration": 60.0, "sections": [{"start": 0, "chapter": "A"}],
                    "words": [{"word": "Hello", "start": 0.0, "end": 0.3, "unit": "u0"}, {"word": "world.", "start": 0.3, "end": 0.6, "unit": "u0"}],
                    "shots": [{"index": 0, "start": 0.0, "duration": 5.0, "src": "boss", "seek": 6.0, "seek_end": 11.0, "sound": False, "unit": "u0", "anchor": ""}]}
        logs = {"boss": {"scenes": [{"index": 3, "start": 5.0, "end": 12.0, "description": "Omega Red close-up", "kind": "cutscene",
                                     "dialogue": [{"start": 6.5, "end": 8.0, "text": "Now look at you.", "speaker": "Omega Red"}]}]}}
        d = review.digest(plan, timeline, logs)
        self.assertEqual(d["shots"][0]["on_screen"], "Omega Red close-up")
        self.assertEqual(d["shots"][0]["said"], ["Omega Red: Now look at you."])
        self.assertEqual(d["narration_units"][0]["text"], "Hello world.")
        fake = lambda system, user: {"summary": "s", "quotable_line": "q", "retention_risk": [], "findings": [{"severity": "fix", "at": 3, "where": "u0", "kind": "clarity", "issue": "i", "suggestion": "x"}]}  # noqa: E731
        res = review.director_review(plan, timeline, logs, call=fake)
        md = review.markdown(res)
        self.assertIn("| 1 | fix | 3 |", md)
        self.assertIn("Story spine", md)


if __name__ == "__main__":
    unittest.main()
