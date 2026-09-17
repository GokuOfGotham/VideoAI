"""Director tools on the command line.

    python director_tool.py index <video> --out work/scene_log/boss --label boss --subtitle-zone 0.16,0.815,0.69,0.055
    python director_tool.py find work/scene_log/boss/scene_log.json "omega red red coils close-up"
    python director_tool.py excerpts work/scene_log/boss/scene_log.json --src boss --brief "carbonadium drain healing Team X" --out EXCERPTS.md
    python director_tool.py spine-template --duration 900 > story_spine.json
    python director_tool.py check plan.json [--duration 903]
    python director_tool.py review output/<video>/main_production_plan.json output/<video>/work/main_timeline.json \
        --scene-log boss=work/scene_log/boss/scene_log.json --out output/<video>/DIRECTOR_REVIEW.md

The subtitle zone is x,y,w,h as fractions of the frame (the crop used on Marvel's Wolverine's 4K
captures was 600,1760 / 2640×120 of 3840×2160 → 0.156,0.815,0.6875,0.0556).
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dotenv import load_dotenv  # noqa: E402

load_dotenv(Path(__file__).resolve().parent / ".env")
from videoai_director import story  # noqa: E402

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")


def cmd_index(a):
    from videoai_director import scene_index
    zone = tuple(float(v) for v in a.subtitle_zone.split(",")) if a.subtitle_zone else None
    log = scene_index.index_source(Path(a.video), Path(a.out), label=a.label or "", subtitle_zone=zone, vision=not a.no_vision,
                                   transcribe_audio=not a.no_transcribe, max_shot=a.max_shot, threshold=a.threshold, workers=a.workers, limit=a.limit,
                                   cast=a.cast, redo_vision=a.redo_vision)
    print(f"{len(log['scenes'])} scenes, {len(log['lines'])} dialogue lines -> {Path(a.out) / 'scene_log.json'}")


def cmd_find(a):
    from videoai_director import scene_index
    for sc in scene_index.find(scene_index.load(Path(a.scene_log)), a.query, min_len=a.min_len, limit=a.limit):
        said = " / ".join((f"{d['speaker']}: " if d.get("speaker") else "") + d["text"] for d in sc.get("dialogue", []))
        print(f"[{sc['score']}] #{sc['index']} {sc['start']:.1f}-{sc['end']:.1f} {sc.get('kind','')}/{sc.get('energy','')}  {sc.get('description','')}  {('| ' + said) if said else ''}")


def cmd_excerpts(a):
    from videoai_director import excerpts, scene_index
    rows = excerpts.candidates(scene_index.load(Path(a.scene_log)), src=a.src, brief=a.brief, max_seconds=a.max_seconds, limit=a.limit)
    md = excerpts.markdown(rows, f"Candidate excerpts — {a.src or Path(a.scene_log).parent.name}")
    if a.out:
        Path(a.out).write_text(md, encoding="utf-8"); Path(a.out).with_suffix(".json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"{len(rows)} candidates -> {a.out}")
    else:
        print(md)


def cmd_spine_template(a):
    print(json.dumps(story.template(a.duration), indent=1))


def cmd_check(a):
    plan = json.loads(Path(a.plan).read_text(encoding="utf-8"))
    spine = plan.get("story_spine") or plan
    duration = a.duration or plan.get("duration")
    if not duration:
        raise SystemExit("pass --duration or a plan with a duration field")
    result = story.validate_spine(spine, float(duration), plan.get("narration_script"))
    print(story.report(result))
    raise SystemExit(1 if result["errors"] else 0)


def cmd_review(a):
    from videoai_director import review, scene_index
    plan = json.loads(Path(a.plan).read_text(encoding="utf-8")); timeline = json.loads(Path(a.timeline).read_text(encoding="utf-8"))
    logs = {}
    for spec in a.scene_log or []:
        key, _, path = spec.partition("=")
        logs[key] = scene_index.load(Path(path))
    result = review.director_review(plan, timeline, logs, model=a.model or review.REVIEW_MODEL)
    md = review.markdown(result, f"Director review — {plan.get('title', '')}")
    if a.out:
        Path(a.out).write_text(md, encoding="utf-8"); Path(a.out).with_suffix(".json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"review -> {a.out}")
    else:
        print(md)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0]); sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("index", help="build a scene log for one source"); p.add_argument("video"); p.add_argument("--out", required=True); p.add_argument("--label", default="")
    p.add_argument("--subtitle-zone", default="", help="x,y,w,h fractions of the frame where the source burns its subtitles")
    p.add_argument("--no-vision", action="store_true"); p.add_argument("--no-transcribe", action="store_true")
    p.add_argument("--cast", default="", help="who may appear and what they look like, e.g. 'Logan: bearded, yellow vest; Omega Red: pale, white hair, coils'")
    p.add_argument("--redo-vision", action="store_true", help="re-describe every scene (keeps thumbnails and transcripts)")
    p.add_argument("--max-shot", type=float, default=10.0); p.add_argument("--threshold", type=float, default=0.30); p.add_argument("--workers", type=int, default=4); p.add_argument("--limit", type=int, default=None)
    p.set_defaults(fn=cmd_index)
    p = sub.add_parser("find", help="scenes matching a description"); p.add_argument("scene_log"); p.add_argument("query"); p.add_argument("--min-len", type=float, default=0.0); p.add_argument("--limit", type=int, default=8); p.set_defaults(fn=cmd_find)
    p = sub.add_parser("excerpts", help="ranked candidate excerpts from a scene log"); p.add_argument("scene_log"); p.add_argument("--src", default=""); p.add_argument("--brief", action="append", default=[])
    p.add_argument("--max-seconds", type=float, default=20.0); p.add_argument("--limit", type=int, default=40); p.add_argument("--out", default=""); p.set_defaults(fn=cmd_excerpts)
    p = sub.add_parser("spine-template", help="print a story spine skeleton"); p.add_argument("--duration", type=float, default=600.0); p.set_defaults(fn=cmd_spine_template)
    p = sub.add_parser("check", help="validate a plan's story spine"); p.add_argument("plan"); p.add_argument("--duration", type=float, default=None); p.set_defaults(fn=cmd_check)
    p = sub.add_parser("review", help="director's review of a plan + timeline"); p.add_argument("plan"); p.add_argument("timeline"); p.add_argument("--scene-log", action="append", help="key=path, key = the source key used in the timeline")
    p.add_argument("--model", default=""); p.add_argument("--out", default=""); p.set_defaults(fn=cmd_review)
    a = ap.parse_args(argv); a.fn(a)


if __name__ == "__main__":
    main()
