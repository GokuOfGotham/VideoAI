"""Picture editor: a machine-readable timeline the agent can inspect and change.

The timeline is plain JSON so any model can read it before deciding a cut:

    {"name": "...", "fps": 30, "width": 1920, "height": 1080,
     "tracks": [{"id": "V1", "kind": "video", "clips": [
         {"id": "c1", "name": "hook", "src": "raw.mp4", "src_in": 12.0, "src_out": 15.5,
          "start": 0.0, "speed": 1.0, "audio": "source"}]}],
     "markers": [{"time": 0.0, "name": "HOOK"}],
     "production_review": {...}}

Clip length on the timeline is (src_out - src_in) / speed. Track clips never
overlap; ``apply_edit_action`` keeps that invariant and ripples later clips
when an operation changes a clip's length. ``to_edit_plan`` hands V1 to
``edit_tools.resolve``/``render_segments`` so the render, captions and the
Epidemic finishing pass are the same ones every recipe uses; the timeline is
a front end to them, not a second renderer.
"""

from __future__ import annotations

import copy
import itertools
import re
from fractions import Fraction
from pathlib import Path
from typing import Any, Iterable
from xml.sax.saxutils import escape

from .common import EditRoomError, timecode, write_json

EDIT_ACTIONS = ("insert", "overwrite", "append", "ripple_delete", "lift", "trim", "split",
                "move", "reorder", "set", "add_marker", "remove_marker")


# --- Model --------------------------------------------------------------------


def new_timeline(name: str, *, fps: float = 30.0, width: int = 1920, height: int = 1080,
                 tracks: Iterable[str] = ("V1", "A1")) -> dict[str, Any]:
    return {"name": name, "fps": float(fps), "width": int(width), "height": int(height),
            "tracks": [{"id": t, "kind": "audio" if t.upper().startswith("A") else "video", "clips": []}
                       for t in tracks],
            "markers": [], "production_review": {}}


def clip_length(clip: dict[str, Any]) -> float:
    speed = float(clip.get("speed", 1.0) or 1.0)
    if speed <= 0:
        raise EditRoomError(f"Clip {clip.get('id')} has a non-positive speed.")
    length = (float(clip["src_out"]) - float(clip["src_in"])) / speed + float(clip.get("hold", 0.0))
    if length <= 0:
        raise EditRoomError(f"Clip {clip.get('id')} has no length (src_out must exceed src_in).")
    return length


def clip_end(clip: dict[str, Any]) -> float:
    return float(clip["start"]) + clip_length(clip)


def _track(timeline: dict[str, Any], track_id: str) -> dict[str, Any]:
    for track in timeline["tracks"]:
        if track["id"] == track_id:
            return track
    raise EditRoomError(f"Track {track_id} does not exist; tracks: "
                        f"{', '.join(t['id'] for t in timeline['tracks'])}.")


def _find(timeline: dict[str, Any], clip_id: str) -> tuple[dict[str, Any], int]:
    for track in timeline["tracks"]:
        for index, clip in enumerate(track["clips"]):
            if clip["id"] == clip_id:
                return track, index
    raise EditRoomError(f"Clip {clip_id} is not on the timeline.")


def _next_id(timeline: dict[str, Any]) -> str:
    taken = {c["id"] for t in timeline["tracks"] for c in t["clips"]}
    for n in itertools.count(1):
        if f"c{n}" not in taken:
            return f"c{n}"
    raise AssertionError  # pragma: no cover


def _normalise(track: dict[str, Any]) -> None:
    track["clips"].sort(key=lambda c: float(c["start"]))
    for clip in track["clips"]:
        clip["start"] = round(float(clip["start"]), 3)
        clip["src_in"] = round(float(clip["src_in"]), 3)
        clip["src_out"] = round(float(clip["src_out"]), 3)


def validate_timeline(timeline: dict[str, Any]) -> dict[str, Any]:
    """Raises on overlaps or malformed clips; returns a summary."""
    for key in ("fps", "width", "height", "tracks"):
        if key not in timeline:
            raise EditRoomError(f"Timeline is missing '{key}'.")
    seen: set[str] = set()
    for track in timeline["tracks"]:
        cursor = -1e-9
        for clip in sorted(track["clips"], key=lambda c: float(c["start"])):
            for key in ("id", "src", "src_in", "src_out", "start"):
                if key not in clip:
                    raise EditRoomError(f"Clip on {track['id']} is missing '{key}'.")
            if clip["id"] in seen:
                raise EditRoomError(f"Clip id {clip['id']} is used twice.")
            seen.add(clip["id"])
            if float(clip["start"]) < cursor - 1e-6:
                raise EditRoomError(f"Clip {clip['id']} overlaps the previous clip on {track['id']}.")
            cursor = clip_end(clip)
    return get_timeline_state(timeline)


def timeline_duration(timeline: dict[str, Any]) -> float:
    ends = [clip_end(c) for t in timeline["tracks"] for c in t["clips"]]
    return round(max(ends), 3) if ends else 0.0


def get_timeline_state(timeline: dict[str, Any]) -> dict[str, Any]:
    """The sequence as the agent should read it before deciding a change."""
    fps = float(timeline["fps"])
    tracks = []
    for track in timeline["tracks"]:
        clips = []
        for clip in sorted(track["clips"], key=lambda c: float(c["start"])):
            end = clip_end(clip)
            clips.append({**clip, "end": round(end, 3), "length": round(clip_length(clip), 3),
                          "timecode_in": timecode(clip["start"], fps), "timecode_out": timecode(end, fps)})
        gaps = [{"start": round(a["end"], 3), "end": round(float(b["start"]), 3)}
                for a, b in zip(clips, clips[1:]) if float(b["start"]) - a["end"] > 1e-3]
        tracks.append({"id": track["id"], "kind": track["kind"], "clip_count": len(clips),
                       "clips": clips, "gaps": gaps})
    duration = timeline_duration(timeline)
    return {"name": timeline.get("name"), "fps": fps, "width": timeline["width"],
            "height": timeline["height"], "duration": duration,
            "duration_timecode": timecode(duration, fps), "tracks": tracks,
            "markers": sorted(timeline.get("markers", []), key=lambda m: m["time"]),
            "sources": sorted({c["src"] for t in timeline["tracks"] for c in t["clips"]}),
            "production_review": timeline.get("production_review", {})}


# --- ApplyEditAction ----------------------------------------------------------


def _ripple(track: dict[str, Any], from_time: float, delta: float, *, exclude: str | None = None) -> None:
    for clip in track["clips"]:
        if clip["id"] != exclude and float(clip["start"]) >= from_time - 1e-6:
            clip["start"] = round(float(clip["start"]) + delta, 3)


def _make_clip(timeline: dict[str, Any], spec: dict[str, Any]) -> dict[str, Any]:
    clip = {"speed": 1.0, "audio": "source", **spec}
    clip.setdefault("id", _next_id(timeline))
    clip.setdefault("name", clip["id"])
    for key in ("src", "src_in", "src_out"):
        if key not in clip:
            raise EditRoomError(f"A new clip needs '{key}'.")
    clip_length(clip)
    return clip


def apply_edit_action(timeline: dict[str, Any], action: dict[str, Any]) -> dict[str, Any]:
    """Applies one timeline operation and returns the new state.

    Actions (``{"action": name, ...}``):
      insert        track, at, clip{src, src_in, src_out,...}: ripple later clips right.
      overwrite     track, at, clip: replaces whatever is under the new clip.
      append        track, clip: after the last clip.
      ripple_delete clip_id: remove and close the gap.
      lift          clip_id: remove and leave the gap.
      trim          clip_id, src_in and/or src_out (ripples the rest of the track).
      split         clip_id, at (timeline seconds): two clips.
      move          clip_id, to (timeline seconds; must land in a free range).
      reorder       track, order [clip ids]: re-sequence the track without gaps.
      set           clip_id, fields{...}: name, speed, audio, fx, text, cx...
      add_marker    time, name.   remove_marker  name.
    """
    timeline = copy.deepcopy(timeline)
    name = action.get("action")
    if name not in EDIT_ACTIONS:
        raise EditRoomError(f"Unknown action '{name}'; choose from {', '.join(EDIT_ACTIONS)}.")

    if name in ("insert", "overwrite", "append"):
        track = _track(timeline, action.get("track", "V1"))
        clip = _make_clip(timeline, dict(action["clip"]))
        if name == "append":
            at = max((clip_end(c) for c in track["clips"]), default=0.0)
        else:
            at = float(action["at"])
        clip["start"] = round(at, 3)
        length = clip_length(clip)
        if name == "insert":
            for existing in track["clips"]:
                if float(existing["start"]) < at < clip_end(existing) - 1e-6:
                    raise EditRoomError(f"Insert point {at} is inside clip {existing['id']}; split it first.")
            _ripple(track, at, length)
        elif name == "overwrite":
            survivors = [clip]
            taken = {c["id"] for t in timeline["tracks"] for c in t["clips"]} | {clip["id"]}

            def fresh_id() -> str:
                n = next(n for n in itertools.count(1) if f"c{n}" not in taken)
                taken.add(f"c{n}")
                return f"c{n}"

            for existing in track["clips"]:
                s, e = float(existing["start"]), clip_end(existing)
                if e <= at + 1e-6 or s >= at + length - 1e-6:
                    survivors.append(existing)
                    continue
                speed = float(existing.get("speed", 1.0) or 1.0)
                if s < at:  # keep the head
                    head = {**existing, "src_out": round(float(existing["src_in"]) + (at - s) * speed, 3)}
                    head.pop("hold", None)
                    survivors.append(head)
                if e > at + length:  # keep the tail
                    tail = {**existing, "id": fresh_id() if s < at else existing["id"],
                            "start": round(at + length, 3),
                            "src_in": round(float(existing["src_in"]) + (at + length - s) * speed, 3)}
                    survivors.append(tail)
            track["clips"] = survivors
        if name != "overwrite":
            track["clips"].append(clip)
        _normalise(track)

    elif name in ("ripple_delete", "lift"):
        track, index = _find(timeline, action["clip_id"])
        clip = track["clips"].pop(index)
        if name == "ripple_delete":
            _ripple(track, clip_end(clip), -clip_length(clip))

    elif name == "trim":
        track, index = _find(timeline, action["clip_id"])
        clip = track["clips"][index]
        old_length = clip_length(clip)
        old_end = clip_end(clip)
        if "src_in" in action:
            clip["src_in"] = float(action["src_in"])
        if "src_out" in action:
            clip["src_out"] = float(action["src_out"])
        delta = clip_length(clip) - old_length
        _ripple(track, old_end, delta, exclude=clip["id"])
        _normalise(track)

    elif name == "split":
        track, index = _find(timeline, action["clip_id"])
        clip = track["clips"][index]
        at = float(action["at"])
        if not float(clip["start"]) + 1e-3 < at < clip_end(clip) - 1e-3:
            raise EditRoomError(f"Split point {at} is not inside clip {clip['id']}.")
        speed = float(clip.get("speed", 1.0) or 1.0)
        cut = float(clip["src_in"]) + (at - float(clip["start"])) * speed
        hold = clip.pop("hold", 0.0)
        second = {**clip, "id": _next_id(timeline), "name": f"{clip.get('name', clip['id'])}_b",
                  "start": round(at, 3), "src_in": round(cut, 3)}
        if hold:
            second["hold"] = hold
        clip["src_out"] = round(cut, 3)
        track["clips"].insert(index + 1, second)

    elif name == "move":
        track, index = _find(timeline, action["clip_id"])
        clip = track["clips"].pop(index)
        clip["start"] = round(float(action["to"]), 3)
        end = clip_end(clip)
        for other in track["clips"]:
            if float(other["start"]) < end - 1e-6 and clip_end(other) > float(clip["start"]) + 1e-6:
                track["clips"].insert(index, clip)
                raise EditRoomError(f"Moving {clip['id']} to {clip['start']} would overlap {other['id']}.")
        track["clips"].append(clip)
        _normalise(track)

    elif name == "reorder":
        track = _track(timeline, action.get("track", "V1"))
        order = list(action["order"])
        ids = [c["id"] for c in track["clips"]]
        if sorted(order) != sorted(ids):
            raise EditRoomError("reorder needs every clip id on the track exactly once.")
        by_id = {c["id"]: c for c in track["clips"]}
        cursor = 0.0
        track["clips"] = []
        for clip_id in order:
            clip = by_id[clip_id]
            clip["start"] = round(cursor, 3)
            cursor += clip_length(clip)
            track["clips"].append(clip)

    elif name == "set":
        track, index = _find(timeline, action["clip_id"])
        clip = track["clips"][index]
        fields = dict(action.get("fields", {}))
        for key in ("id", "start"):
            if key in fields:
                raise EditRoomError(f"Use move/split instead of setting '{key}'.")
        old_end = clip_end(clip)
        old_length = clip_length(clip)
        clip.update(fields)
        _ripple(track, old_end, clip_length(clip) - old_length, exclude=clip["id"])
        _normalise(track)

    elif name == "add_marker":
        timeline.setdefault("markers", []).append({"time": round(float(action["time"]), 3),
                                                   "name": str(action["name"])})
    elif name == "remove_marker":
        timeline["markers"] = [m for m in timeline.get("markers", []) if m["name"] != action["name"]]

    validate_timeline(timeline)
    return timeline


def apply_edit_actions(timeline: dict[str, Any], actions: Iterable[dict[str, Any]]) -> dict[str, Any]:
    for action in actions:
        timeline = apply_edit_action(timeline, action)
    return timeline


# --- BuildAssembly ------------------------------------------------------------


def _score_segment(text: str, keywords: list[str]) -> int:
    lowered = text.lower()
    return sum(1 for k in keywords if k and k.lower() in lowered)


def build_assembly(source: str | Path, transcript: dict[str, Any], *, brief: str | None = None,
                   keywords: Iterable[str] = (), highlights: Iterable[tuple[float, float]] = (),
                   keep_ranges: Iterable[tuple[float, float]] = (), target_seconds: float | None = None,
                   lead: float = 0.1, tail: float = 0.3, fps: float = 30.0, width: int = 1920,
                   height: int = 1080, name: str = "assembly") -> dict[str, Any]:
    """A rough cut from transcript highlights, explicit ranges, or a natural-language brief.

    Priority: explicit `highlights` (src in/out pairs) are used as given;
    otherwise transcript segments are scored by `keywords` (or the significant
    words of `brief`) and taken in source order until `target_seconds` is
    filled. `keep_ranges` (from ``ingest.keep_ranges``) limits the assembly to
    what survives silence removal. Segments are padded by `lead`/`tail` so
    cuts land on word boundaries with air, as the excerpt rules require.
    """
    timeline = new_timeline(name, fps=fps, width=width, height=height)
    picks: list[tuple[float, float, str]] = []
    highlights = list(highlights)
    if highlights:
        picks = [(float(a), float(b), f"highlight_{i + 1}") for i, (a, b) in enumerate(highlights)]
    else:
        words = [w for w in re.findall(r"[a-z0-9']+", (brief or "").lower()) if len(w) > 3]
        keywords = list(keywords) or words
        segments = transcript.get("segments") or []
        scored = [(s, _score_segment(s.get("text", ""), keywords)) for s in segments]
        chosen = [s for s, score in scored if score > 0] if keywords else list(segments)
        chosen.sort(key=lambda s: float(s["start"]))
        budget = target_seconds
        for segment in chosen:
            a, b = float(segment["start"]) - lead, float(segment["end"]) + tail
            if budget is not None and budget - (b - a) < 0 and picks:
                break
            picks.append((max(0.0, a), b, segment.get("text", "")[:40] or f"seg_{len(picks) + 1}"))
            if budget is not None:
                budget -= b - a
    source_length = None
    if Path(source).exists():
        from .common import media_duration
        try:
            source_length = media_duration(source)
        except EditRoomError:
            source_length = None
    if source_length:
        picks = [(min(a, source_length), min(b, source_length), label) for a, b, label in picks]
        picks = [(a, b, label) for a, b, label in picks if b - a > 0.2]
    keep = list(keep_ranges)
    if keep:
        trimmed = []
        for a, b, label in picks:
            for ka, kb in keep:
                lo, hi = max(a, ka), min(b, kb)
                if hi - lo > 0.2:
                    trimmed.append((lo, hi, label))
        picks = trimmed
    # merge picks that touch or overlap
    merged: list[list[Any]] = []
    for a, b, label in sorted(picks):
        if merged and a <= merged[-1][1] + 0.05:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b, label])
    for a, b, label in merged:
        timeline = apply_edit_action(timeline, {"action": "append", "track": "V1", "clip": {
            "name": re.sub(r"[^A-Za-z0-9_]+", "_", label).strip("_") or "clip",
            "src": str(source), "src_in": round(a, 3), "src_out": round(b, 3)}})
    if not merged:
        raise EditRoomError("No segments matched the brief/keywords; widen them or pass highlights.")
    timeline["markers"] = [{"time": 0.0, "name": "HOOK"}]
    return timeline


# --- Bridges ------------------------------------------------------------------


def to_edit_plan(timeline: dict[str, Any], track_id: str = "V1") -> list[tuple]:
    """V1 as ``edit_tools.resolve`` plan entries; gaps become black segments."""
    track = _track(timeline, track_id)
    plan, cursor = [], 0.0
    for clip in sorted(track["clips"], key=lambda c: float(c["start"])):
        if float(clip["start"]) - cursor > 1e-3:
            plan.append((f"gap_{len(plan) + 1}", None, round(float(clip["start"]) - cursor, 3), {}))
        options = {k: v for k, v in clip.items()
                   if k not in ("id", "name", "src_in", "src_out", "start")}
        plan.append((clip.get("name", clip["id"]), clip["src_in"], clip["src_out"], options))
        cursor = clip_end(clip)
    return plan


def export_xml(timeline: dict[str, Any], output: str | Path | None = None) -> str:
    """FCPXML 1.9 for DaVinci Resolve / Premiere (via XML import) handoff."""
    validate_timeline(timeline)
    fps = Fraction(str(timeline["fps"])).limit_denominator(1001)
    if float(fps) == 29.97 or (fps.numerator == 2997 and fps.denominator == 100):
        fps = Fraction(30000, 1001)
    frame = Fraction(fps.denominator, fps.numerator)

    def t(seconds: float) -> str:
        frames = round(Fraction(str(round(seconds, 6))) / frame)
        return f"{frames * frame.numerator}/{frame.denominator}s"

    sources = sorted({c["src"] for tr in timeline["tracks"] for c in tr["clips"]})
    asset_ids = {src: f"r{i + 2}" for i, src in enumerate(sources)}
    duration = timeline_duration(timeline)
    out = ['<?xml version="1.0" encoding="UTF-8"?>', "<!DOCTYPE fcpxml>", '<fcpxml version="1.9">',
           "  <resources>",
           f'    <format id="r1" name="FFVideoFormat{timeline["height"]}p{float(fps):g}" '
           f'frameDuration="{frame.numerator}/{frame.denominator}s" width="{timeline["width"]}" '
           f'height="{timeline["height"]}"/>']
    for src, asset_id in asset_ids.items():
        path = Path(src)
        uri = path.resolve().as_uri() if path.is_absolute() or path.exists() else escape(src)
        out.append(f'    <asset id="{asset_id}" name="{escape(path.name)}" src="{escape(uri)}" '
                   f'hasVideo="1" hasAudio="1" format="r1"/>')
    out += ["  </resources>", "  <library>", f'    <event name="{escape(str(timeline.get("name", "VideoAI")))}">',
            f'      <project name="{escape(str(timeline.get("name", "VideoAI")))}">',
            f'        <sequence format="r1" duration="{t(duration)}" tcStart="0s" tcFormat="NDF">',
            "          <spine>"]
    lanes = [tr for tr in timeline["tracks"] if tr["clips"]]
    for lane_index, track in enumerate(lanes):
        cursor = 0.0
        for clip in sorted(track["clips"], key=lambda c: float(c["start"])):
            start = float(clip["start"])
            if lane_index == 0 and start - cursor > 1e-3:
                out.append(f'            <gap name="Gap" offset="{t(cursor)}" duration="{t(start - cursor)}"/>')
            lane = "" if lane_index == 0 else f' lane="{lane_index if track["kind"] == "video" else -lane_index}"'
            speed = float(clip.get("speed", 1.0) or 1.0)
            out.append(f'            <asset-clip name="{escape(str(clip.get("name", clip["id"])))}" '
                       f'ref="{asset_ids[clip["src"]]}" offset="{t(start)}" start="{t(float(clip["src_in"]))}" '
                       f'duration="{t(clip_length(clip))}"{lane} tcFormat="NDF">')
            if speed != 1.0:
                out.append(f'              <timeMap><timept time="0s" value="0s" interp="smooth2"/>'
                           f'<timept time="{t(clip_length(clip))}" value="{t(float(clip["src_out"]) - float(clip["src_in"]))}" interp="smooth2"/></timeMap>')
            if clip.get("audio") == "mute":
                out.append('              <adjust-volume amount="-96dB"/>')
            out.append("            </asset-clip>")
            cursor = clip_end(clip)
    for marker in sorted(timeline.get("markers", []), key=lambda m: m["time"]):
        out.append(f'            <!-- marker {escape(str(marker["name"]))} at {t(float(marker["time"]))} -->')
    out += ["          </spine>", "        </sequence>", "      </project>", "    </event>",
            "  </library>", "</fcpxml>", ""]
    xml = "\n".join(out)
    if output:
        Path(output).parent.mkdir(parents=True, exist_ok=True)
        Path(output).write_text(xml, encoding="utf-8")
    return xml


def export_edl(timeline: dict[str, Any], output: str | Path | None = None, track_id: str = "V1") -> str:
    """CMX3600 EDL for V1: the universal fallback every NLE imports."""
    fps = float(timeline["fps"])
    lines = [f"TITLE: {timeline.get('name', 'VideoAI')}", "FCM: NON-DROP FRAME", ""]
    track = _track(timeline, track_id)
    sources = sorted({c["src"] for c in track["clips"]})
    reels = {src: f"{i + 1:03d}" for i, src in enumerate(sources)}
    for index, clip in enumerate(sorted(track["clips"], key=lambda c: float(c["start"])), start=1):
        rec_in, rec_out = float(clip["start"]), clip_end(clip)
        lines.append(f"{index:03d}  {reels[clip['src']]}      V     C        "
                     f"{timecode(clip['src_in'], fps)} {timecode(clip['src_out'], fps)} "
                     f"{timecode(rec_in, fps)} {timecode(rec_out, fps)}")
        lines.append(f"* FROM CLIP NAME: {Path(clip['src']).name}")
        if float(clip.get("speed", 1.0) or 1.0) != 1.0:
            lines.append(f"M2   {reels[clip['src']]}       {fps * float(clip['speed']):.1f}   {timecode(clip['src_in'], fps)}")
        lines.append("")
    text = "\n".join(lines)
    if output:
        Path(output).parent.mkdir(parents=True, exist_ok=True)
        Path(output).write_text(text, encoding="utf-8")
    return text


def save_timeline(timeline: dict[str, Any], path: str | Path) -> Path:
    validate_timeline(timeline)
    return write_json(path, timeline)
