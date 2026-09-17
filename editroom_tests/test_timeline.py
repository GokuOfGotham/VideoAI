"""Timeline model: actions keep clips non-overlapping and exports stay consistent."""

import unittest

from videoai_editroom import EditRoomError
from videoai_editroom import timeline as tl


def _clip(name, a, b, **extra):
    return {"name": name, "src": "raw.mp4", "src_in": a, "src_out": b, **extra}


class TimelineActionTests(unittest.TestCase):
    def setUp(self):
        self.t = tl.new_timeline("test")
        for name, a, b in (("one", 0, 2), ("two", 10, 13), ("three", 20, 21)):
            self.t = tl.apply_edit_action(self.t, {"action": "append", "clip": _clip(name, a, b)})

    def starts(self):
        return [(c["name"], c["start"], round(c["end"], 3)) for c in tl.get_timeline_state(self.t)["tracks"][0]["clips"]]

    def test_append_sequences_without_gaps(self):
        self.assertEqual(self.starts(), [("one", 0.0, 2.0), ("two", 2.0, 5.0), ("three", 5.0, 6.0)])
        self.assertEqual(tl.timeline_duration(self.t), 6.0)

    def test_insert_ripples_later_clips(self):
        t = tl.apply_edit_action(self.t, {"action": "insert", "at": 2.0, "clip": _clip("x", 40, 41.5)})
        names = [(c["name"], c["start"]) for c in t["tracks"][0]["clips"]]
        self.assertEqual(names, [("one", 0.0), ("x", 2.0), ("two", 3.5), ("three", 6.5)])

    def test_insert_inside_clip_is_refused(self):
        with self.assertRaises(EditRoomError):
            tl.apply_edit_action(self.t, {"action": "insert", "at": 1.0, "clip": _clip("x", 0, 1)})

    def test_overwrite_splits_underlying_clip(self):
        t = tl.apply_edit_action(self.t, {"action": "overwrite", "at": 3.0, "clip": _clip("x", 40, 41)})
        clips = tl.get_timeline_state(t)["tracks"][0]["clips"]
        self.assertEqual([(c["name"], c["start"], c["end"], c["src_in"], c["src_out"]) for c in clips],
                         [("one", 0.0, 2.0, 0.0, 2.0), ("two", 2.0, 3.0, 10.0, 11.0), ("x", 3.0, 4.0, 40.0, 41.0),
                          ("two", 4.0, 5.0, 12.0, 13.0), ("three", 5.0, 6.0, 20.0, 21.0)])
        self.assertEqual(tl.timeline_duration(t), 6.0)

    def test_ripple_delete_closes_gap_and_lift_leaves_it(self):
        two = self.t["tracks"][0]["clips"][1]["id"]
        rippled = tl.apply_edit_action(self.t, {"action": "ripple_delete", "clip_id": two})
        self.assertEqual([c["start"] for c in rippled["tracks"][0]["clips"]], [0.0, 2.0])
        lifted = tl.apply_edit_action(self.t, {"action": "lift", "clip_id": two})
        self.assertEqual([c["start"] for c in lifted["tracks"][0]["clips"]], [0.0, 5.0])
        self.assertEqual(tl.get_timeline_state(lifted)["tracks"][0]["gaps"], [{"start": 2.0, "end": 5.0}])

    def test_trim_ripples_and_split_preserves_source_continuity(self):
        two = self.t["tracks"][0]["clips"][1]["id"]
        t = tl.apply_edit_action(self.t, {"action": "trim", "clip_id": two, "src_out": 12.0})
        self.assertEqual([c["start"] for c in t["tracks"][0]["clips"]], [0.0, 2.0, 4.0])
        t = tl.apply_edit_action(t, {"action": "split", "clip_id": two, "at": 3.0})
        a, b = t["tracks"][0]["clips"][1:3]
        self.assertEqual((a["src_in"], a["src_out"], b["src_in"], b["src_out"]), (10.0, 11.0, 11.0, 12.0))
        self.assertEqual((a["start"], b["start"]), (2.0, 3.0))

    def test_split_respects_speed(self):
        t = tl.new_timeline("speed")
        t = tl.apply_edit_action(t, {"action": "append", "clip": _clip("slow", 0, 2, speed=0.5)})
        self.assertEqual(tl.timeline_duration(t), 4.0)
        t = tl.apply_edit_action(t, {"action": "split", "clip_id": "c1", "at": 1.0})
        self.assertEqual(t["tracks"][0]["clips"][0]["src_out"], 0.5)

    def test_reorder_and_move(self):
        ids = [c["id"] for c in self.t["tracks"][0]["clips"]]
        t = tl.apply_edit_action(self.t, {"action": "reorder", "order": [ids[2], ids[0], ids[1]]})
        self.assertEqual([c["name"] for c in t["tracks"][0]["clips"]], ["three", "one", "two"])
        self.assertEqual([c["start"] for c in t["tracks"][0]["clips"]], [0.0, 1.0, 3.0])
        with self.assertRaises(EditRoomError):
            tl.apply_edit_action(self.t, {"action": "move", "clip_id": ids[0], "to": 3.0})
        moved = tl.apply_edit_action(self.t, {"action": "move", "clip_id": ids[2], "to": 9.0})
        self.assertEqual(tl.timeline_duration(moved), 10.0)

    def test_set_cannot_change_identity(self):
        with self.assertRaises(EditRoomError):
            tl.apply_edit_action(self.t, {"action": "set", "clip_id": "c1", "fields": {"start": 4}})
        t = tl.apply_edit_action(self.t, {"action": "set", "clip_id": "c1", "fields": {"audio": "mute", "hold": 1.0}})
        self.assertEqual([c["start"] for c in t["tracks"][0]["clips"]], [0.0, 3.0, 6.0])

    def test_unknown_action_and_overlap_validation(self):
        with self.assertRaises(EditRoomError):
            tl.apply_edit_action(self.t, {"action": "explode"})
        broken = tl.new_timeline("bad")
        broken["tracks"][0]["clips"] = [{"id": "a", **_clip("a", 0, 5), "start": 0.0},
                                        {"id": "b", **_clip("b", 0, 5), "start": 2.0}]
        with self.assertRaises(EditRoomError):
            tl.validate_timeline(broken)

    def test_original_timeline_is_not_mutated(self):
        before = [c["start"] for c in self.t["tracks"][0]["clips"]]
        tl.apply_edit_action(self.t, {"action": "ripple_delete", "clip_id": "c1"})
        self.assertEqual([c["start"] for c in self.t["tracks"][0]["clips"]], before)


class AssemblyAndExportTests(unittest.TestCase):
    TRANSCRIPT = {"segments": [
        {"start": 1.0, "end": 3.0, "text": "The rocket exploded on the pad."},
        {"start": 5.0, "end": 6.0, "text": "Weather was fine."},
        {"start": 8.0, "end": 10.0, "text": "Engineers blamed the rocket's valve."}]}

    def test_brief_selects_matching_segments_with_air(self):
        t = tl.build_assembly("raw.mp4", self.TRANSCRIPT, brief="what happened to the rocket")
        clips = t["tracks"][0]["clips"]
        self.assertEqual([(c["src_in"], c["src_out"]) for c in clips], [(0.9, 3.3), (7.9, 10.3)])
        self.assertEqual(t["markers"], [{"time": 0.0, "name": "HOOK"}])

    def test_target_seconds_and_keep_ranges(self):
        t = tl.build_assembly("raw.mp4", self.TRANSCRIPT, keywords=["rocket"], target_seconds=2.5)
        self.assertEqual(len(t["tracks"][0]["clips"]), 1)
        t = tl.build_assembly("raw.mp4", self.TRANSCRIPT, keywords=["rocket"], keep_ranges=[(0.0, 2.0), (9.0, 12.0)])
        self.assertEqual([(c["src_in"], c["src_out"]) for c in t["tracks"][0]["clips"]], [(0.9, 2.0), (9.0, 10.3)])

    def test_highlights_win_and_empty_match_fails(self):
        t = tl.build_assembly("raw.mp4", self.TRANSCRIPT, highlights=[(4, 5), (4.9, 6)])
        self.assertEqual([(c["src_in"], c["src_out"]) for c in t["tracks"][0]["clips"]], [(4.0, 6.0)])
        with self.assertRaises(EditRoomError):
            tl.build_assembly("raw.mp4", self.TRANSCRIPT, keywords=["submarine"])

    def test_edit_plan_bridge_and_exports(self):
        t = tl.build_assembly("raw.mp4", self.TRANSCRIPT, keywords=["rocket"], fps=29.97)
        t = tl.apply_edit_action(t, {"action": "lift", "clip_id": "c1"})
        plan = tl.to_edit_plan(t)
        self.assertEqual(plan[0][1], None)  # the lifted clip became a black gap
        self.assertAlmostEqual(plan[0][2], 2.4, places=3)
        self.assertEqual(plan[1][3]["src"], "raw.mp4")
        xml = tl.export_xml(t)
        self.assertIn('frameDuration="1001/30000s"', xml)
        self.assertIn('<gap name="Gap" offset="0/30000s"', xml)
        self.assertIn('<asset-clip name="Engineers_blamed', xml)
        edl = tl.export_edl(t)
        self.assertIn("FCM: NON-DROP FRAME", edl)
        self.assertIn("* FROM CLIP NAME: raw.mp4", edl)


if __name__ == "__main__":
    unittest.main()
