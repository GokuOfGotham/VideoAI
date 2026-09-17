"""Command line for the VideoAI editing room departments (see EDITING_ROOM.md).

Every command prints one JSON report so another model or script can read the
result. Renders go through the same edit_tools/graphics_tool path as the
recipes, so the production policy still applies at export.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from videoai_editroom import EditRoomError


def _load(path: str) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def _emit(data: Any) -> None:
    print(json.dumps(data, indent=2, ensure_ascii=False, default=str))


def _pairs(values: list[str]) -> list[tuple[float, float]]:
    out = []
    for value in values:
        a, b = value.split("-", 1) if "-" in value else value.split(":", 1)
        out.append((float(a), float(b)))
    return out


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="command", required=True)

    # Assistant editor
    s = sub.add_parser("transcribe", help="timecoded transcript with words and speaker turns")
    s.add_argument("media"); s.add_argument("--output", required=True)
    s.add_argument("--engine", choices=["whisper", "openai"], default="whisper")
    s.add_argument("--model", default="small"); s.add_argument("--language", default="en")
    s.add_argument("--turn-gap", type=float, default=1.0)
    s.add_argument("--device", choices=["auto", "cuda", "cpu"], default="auto")

    s = sub.add_parser("sync", help="align angles/audio to a reference by waveform")
    s.add_argument("reference"); s.add_argument("angles", nargs="+"); s.add_argument("--output")

    s = sub.add_parser("silence", help="dead air, fillers and retakes as cut candidates")
    s.add_argument("media"); s.add_argument("--transcript"); s.add_argument("--noise-db", type=float, default=-35.0)
    s.add_argument("--min-duration", type=float, default=0.6); s.add_argument("--output")

    s = sub.add_parser("proxies", help="edit-friendly proxies")
    s.add_argument("media", nargs="+"); s.add_argument("--out-dir", required=True)
    s.add_argument("--height", type=int, default=540); s.add_argument("--overwrite", action="store_true")

    # Picture editor
    s = sub.add_parser("timeline", help="inspect or change a timeline JSON")
    s.add_argument("file"); s.add_argument("--action", help="JSON object or @file with one action or a list")
    s.add_argument("--save", help="write the changed timeline here (defaults to the input file)")
    s.add_argument("--new", metavar="NAME", help="create an empty timeline with this name")
    s.add_argument("--fps", type=float, default=30.0); s.add_argument("--width", type=int, default=1920)
    s.add_argument("--height", type=int, default=1080)

    s = sub.add_parser("assemble", help="rough cut from a transcript, brief, keywords or ranges")
    s.add_argument("source"); s.add_argument("--transcript"); s.add_argument("--brief")
    s.add_argument("--keyword", action="append", default=[]); s.add_argument("--highlight", action="append", default=[],
                                                                            help="src in-out, e.g. 12.5-18.0")
    s.add_argument("--silence-report", help="detect_silence output; limits the cut to what survives")
    s.add_argument("--target-seconds", type=float); s.add_argument("--output", required=True)
    s.add_argument("--fps", type=float, default=30.0); s.add_argument("--width", type=int, default=1920)
    s.add_argument("--height", type=int, default=1080)

    s = sub.add_parser("export", help="FCPXML / EDL handoff")
    s.add_argument("file"); s.add_argument("--format", choices=["fcpxml", "edl"], default="fcpxml")
    s.add_argument("--output", required=True)

    s = sub.add_parser("render", help="render V1 through edit_tools (clean edit before graphics_tool)")
    s.add_argument("file"); s.add_argument("--output", required=True); s.add_argument("--work", required=True)

    # VFX & graphics
    s = sub.add_parser("broll", help="contextual B-roll with provenance")
    s.add_argument("query", nargs="?", default=""); s.add_argument("--from-text")
    s.add_argument("--seconds", type=float, default=5.0); s.add_argument("--provider", action="append")
    s.add_argument("--bin"); s.add_argument("--limit", type=int, default=5)

    s = sub.add_parser("captions", help="SRT + house-styled ASS from timed words")
    s.add_argument("words", help="transcript JSON (uses .words) or a plain word list")
    s.add_argument("--output-base", required=True); s.add_argument("--kind", choices=["main", "short"], default="main")
    s.add_argument("--subject", default="default"); s.add_argument("--style", choices=["Narr", "Quote"], default="Narr")
    s.add_argument("--speaker-labels", action="store_true"); s.add_argument("--duration", type=float)

    s = sub.add_parser("reframe", help="track the subject and crop 16:9 to 9:16 (or another aspect)")
    s.add_argument("media"); s.add_argument("--output", required=True); s.add_argument("--aspect", default="9:16")
    s.add_argument("--detector", choices=["auto", "yolo", "motion"], default="auto")
    s.add_argument("--encoder", default="libx264"); s.add_argument("--report")

    # Audio mixer
    s = sub.add_parser("clean", help="denoise / de-hum / de-ess / level dialogue")
    s.add_argument("media"); s.add_argument("--output", required=True)
    s.add_argument("--strength", choices=["light", "medium", "heavy"], default="medium")
    s.add_argument("--target-lufs", type=float, default=-16.0); s.add_argument("--report")

    s = sub.add_parser("duck", help="duck music under dialogue with explicit keyframes")
    s.add_argument("--music", required=True); s.add_argument("--dialogue", required=True)
    s.add_argument("--output", required=True); s.add_argument("--duck-db", type=float, default=-14.0)
    s.add_argument("--music-gain-db", type=float, default=-6.0); s.add_argument("--stem-only", action="store_true")
    s.add_argument("--keyframes")

    s = sub.add_parser("adr", help="replace a dialogue range with a new Cedar take")
    s.add_argument("track"); s.add_argument("--output", required=True); s.add_argument("--text", required=True)
    s.add_argument("--start", type=float, required=True); s.add_argument("--end", type=float, required=True)

    # Colorist
    s = sub.add_parser("match", help="match a shot's colour to a reference shot")
    s.add_argument("reference"); s.add_argument("target"); s.add_argument("--output", required=True)
    s.add_argument("--strength", type=float, default=1.0); s.add_argument("--cube"); s.add_argument("--report")
    s.add_argument("--encoder", default="libx264")

    s = sub.add_parser("lut", help="apply a .cube LUT or a built-in look/transform")
    s.add_argument("media"); s.add_argument("--output", required=True); s.add_argument("--lut", required=True)
    s.add_argument("--encoder", default="libx264")

    sub.add_parser("looks", help="list the built-in looks and transforms")
    return p


def _timeline_command(a: argparse.Namespace) -> Any:
    from videoai_editroom import timeline as tl
    if a.new:
        timeline = tl.new_timeline(a.new, fps=a.fps, width=a.width, height=a.height)
        tl.save_timeline(timeline, a.file)
    else:
        timeline = _load(a.file)
    if not a.action:
        return tl.get_timeline_state(timeline)
    spec = _load(a.action[1:]) if a.action.startswith("@") else json.loads(a.action)
    actions = spec if isinstance(spec, list) else [spec]
    timeline = tl.apply_edit_actions(timeline, actions)
    tl.save_timeline(timeline, a.save or a.file)
    return tl.get_timeline_state(timeline)


def _render_command(a: argparse.Namespace) -> Any:
    import edit_tools
    from videoai_editroom import timeline as tl
    timeline = _load(a.file)
    plan = tl.to_edit_plan(timeline)
    segments = edit_tools.resolve(plan, None, fps=int(timeline["fps"]))
    work = Path(a.work); work.mkdir(parents=True, exist_ok=True)
    pieces = edit_tools.render_segments(segments, work, int(timeline["width"]), int(timeline["height"]),
                                        fps=int(timeline["fps"]))
    edit_tools.concat(pieces, Path(a.output))
    return {"output": a.output, "segments": len(segments), "duration": tl.timeline_duration(timeline),
            "note": "Clean edit only. Finish with graphics_tool.py render (captions, overlays, Epidemic audio) "
                    "and run policy_tool.py check before delivery."}


def main(argv: list[str] | None = None) -> int:
    a = build_parser().parse_args(argv)
    try:
        if a.command == "transcribe":
            from videoai_editroom.ingest import transcribe_media
            _emit(transcribe_media(a.media, language=a.language, engine=a.engine, model_size=a.model,
                                   turn_gap=a.turn_gap, output=a.output, device=a.device))
        elif a.command == "sync":
            from videoai_editroom.ingest import sync_multicam
            _emit(sync_multicam(a.reference, a.angles, output=a.output))
        elif a.command == "silence":
            from videoai_editroom.ingest import detect_silence
            transcript = _load(a.transcript) if a.transcript else None
            _emit(detect_silence(a.media, noise_db=a.noise_db, min_duration=a.min_duration,
                                 transcript=transcript, output=a.output))
        elif a.command == "proxies":
            from videoai_editroom.ingest import generate_proxies
            _emit(generate_proxies(a.media, a.out_dir, height=a.height, overwrite=a.overwrite))
        elif a.command == "timeline":
            _emit(_timeline_command(a))
        elif a.command == "assemble":
            from videoai_editroom import timeline as tl
            from videoai_editroom.ingest import keep_ranges
            transcript = _load(a.transcript) if a.transcript else {"segments": []}
            keep = []
            if a.silence_report:
                report = _load(a.silence_report)
                keep = keep_ranges(report["candidates"], report["duration"])
            timeline = tl.build_assembly(a.source, transcript, brief=a.brief, keywords=a.keyword,
                                         highlights=_pairs(a.highlight), keep_ranges=keep,
                                         target_seconds=a.target_seconds, fps=a.fps, width=a.width, height=a.height,
                                         name=Path(a.output).stem)
            tl.save_timeline(timeline, a.output)
            _emit(tl.get_timeline_state(timeline))
        elif a.command == "export":
            from videoai_editroom import timeline as tl
            timeline = _load(a.file)
            text = tl.export_xml(timeline, a.output) if a.format == "fcpxml" else tl.export_edl(timeline, a.output)
            _emit({"output": a.output, "format": a.format, "bytes": len(text.encode("utf-8"))})
        elif a.command == "render":
            _emit(_render_command(a))
        elif a.command == "broll":
            from videoai_editroom.visual import search_visual_broll
            _emit(search_visual_broll(a.query, seconds=a.seconds, providers=a.provider or ("bin", "youtube"),
                                      bin_dir=a.bin, limit=a.limit, transcript_text=a.from_text))
        elif a.command == "captions":
            from videoai_editroom.visual import generate_captions
            data = _load(a.words)
            words = data["words"] if isinstance(data, dict) else data
            _emit(generate_captions(words, output_base=a.output_base, kind=a.kind, subject=a.subject,
                                    style=a.style, speaker_labels=a.speaker_labels, duration=a.duration))
        elif a.command == "reframe":
            from videoai_editroom.visual import auto_reframe
            _emit(auto_reframe(a.media, a.output, aspect=a.aspect, detector=a.detector, encoder=a.encoder,
                               report=a.report))
        elif a.command == "clean":
            from videoai_editroom.audio import clean_dialogue
            _emit(clean_dialogue(a.media, a.output, strength=a.strength, target_lufs=a.target_lufs, report=a.report))
        elif a.command == "duck":
            from videoai_editroom.audio import apply_audio_ducking
            _emit(apply_audio_ducking(a.music, a.dialogue, a.output, duck_db=a.duck_db,
                                      music_gain_db=a.music_gain_db, mix=not a.stem_only, keyframes_out=a.keyframes))
        elif a.command == "adr":
            from videoai_editroom.audio import generate_adr
            _emit(generate_adr(a.track, a.output, text=a.text, start=a.start, end=a.end))
        elif a.command == "match":
            from videoai_editroom.color import match_color
            _emit(match_color(a.reference, a.target, a.output, strength=a.strength, cube_out=a.cube,
                              report=a.report, encoder=a.encoder))
        elif a.command == "lut":
            from videoai_editroom.color import apply_lut
            _emit(apply_lut(a.media, a.output, lut=a.lut, encoder=a.encoder))
        elif a.command == "looks":
            from videoai_editroom.color import BUILTIN_LOOKS
            _emit(BUILTIN_LOOKS)
    except (EditRoomError, OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        _emit({"status": "failed", "error": f"{type(exc).__name__}: {exc}"})
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
