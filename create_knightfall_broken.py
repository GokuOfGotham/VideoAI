"""Knightfall — the night Bane broke Batman. Long form (16:9) and short (9:16).

Both cuts are built on the scene's own audio: Bane's monologue, the score,
and the scream are the point, so narration (the approved Cedar preset) only
lands in the dialogue-free windows and the source is ducked under it. The
slam onto Bane's knee gets a slow-motion treatment with a shake and flash;
the scream is left at full speed because a stretched scream sounds fake.

Timeline positions are derived from the segment list, so narration cues,
dialogue captions, and graphics cues all stay aligned if a segment changes.
The clean edit is finished through ``graphics_tool.py`` (captions, overlays,
and the required Epidemic music and effects).

    python create_knightfall_broken.py                # both cuts
    python create_knightfall_broken.py --profile short --no-finish
"""

import argparse
import glob
import json
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional

from dotenv import load_dotenv

from edit_tools import (clamp_overlays, compile_captions, concat, finish, mix_narration, place_lines,
                        render_segments, resolve, seg_by_name, timeline_words, words_from_lines)
from narration_tools import narrate_line

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = PROJECT_ROOT / "output" / "Knightfall_Broken"
GAMING_DIR = os.getenv("GAMING_VIDEOS_DIR", os.path.join(os.getenv("MEDIA_ROOT", "M:/Videos"), "Gaming"))
SOURCE = next(iter(glob.glob(os.path.join(GAMING_DIR, "Bane Breaks Batman*Knightfall*.mp4"))), None)

FPS = 30
ACCENT = "#F3D340"  # Batman yellow on the gaming preset's dark panels

# The scene's dialogue, timed by hand against two transcription passes.
# Whisper cannot be trusted on this audio (it heard "Trimmed w Bruce" for
# "I have dreamt of you, Bruce", and put "break you" a second late), and the
# captions have to be right. Lines whose wording is unclear are left out.
DIALOGUE = [
    (30.2, 33.3, "I have dreamt of you, Bruce."),
    (34.1, 36.6, "I've dreamt of your family..."),
    (36.9, 42.3, "...of the strength your father must have had to build his empire."),
    (44.3, 49.2, "An empire you are not fit to rule, because you lack the strength."),
    (50.8, 53.8, "The strength to save Tim."),
    (56.0, 57.0, "Alfred."),
    (58.6, 60.0, "The city."),
    (62.4, 63.2, "Jason."),
    (67.1, 68.0, "Jason."),
    (69.5, 73.6, "The strength to save your parents."),
    (74.3, 78.4, "Oh, how you let them die, Bruce..."),
    (78.5, 81.9, "...while you sat in an alley, mewling like a calf..."),
    (82.1, 88.4, "...as your parents bled, and their murderer disappeared into the night."),
    (88.6, 93.0, "You must be glad they aren't alive to see what you've become."),
    (93.2, 97.4, "To see what you've allowed Gotham to become."),
    (99.1, 100.9, "Enough with your voice."),
    (101.4, 103.2, "Face me with your fists."),
    (118.8, 121.3, "Go to hell."),
    (122.2, 123.8, "I am Bane."),
    (123.9, 128.4, "I could kill you... but death would only end your agony..."),
    (128.6, 131.3, "...and silence your shame."),
    (131.6, 135.4, "Instead... I will simply—"),
    (146.0, 148.3, "...break you."),
    (166.3, 167.2, "Bruce."),
    (174.6, 177.0, "Get one of those floodlights on the second-story roof."),
    (184.2, 186.4, "Where the hell is this guy?"),
    (186.8, 193.3, "Now, Gotham... you must do what you haven't done for a generation."),
    (194.3, 195.8, "Fend for yourself."),
    (217.1, 218.5, "Take him out!"),
    (240.4, 243.0, "That can't— that can't be Batman, can it?"),
    (243.1, 244.6, "What's going to happen to the city?"),
    (244.7, 247.0, "Get back! Everyone, get back! Move!"),
    (250.7, 252.1, "Good God."),
    (252.5, 255.8, "This place is about to become hell on Earth."),
]


# --- Segment plans ------------------------------------------------------------
#
# (name, src_in, src_out, options). `speed` < 1 slows; `audio` is "source"
# (kept, captioned), "bed" (kept low, uncaptioned — for under narration) or
# "mute"; `fx` "hit" adds the impact shake and flash; `cx` centres the 9:16
# crop; `hold` freezes the last frame; ("name", None, seconds, {}) is black.

LONG = [
    ("cold_open", 136.0, 141.6, {}),                    # lift, slam, scream: the hook
    ("title", None, 3.2, {}),                           # black, title card
    ("cave", 0.0, 29.5, {}),                            # Batman limps home
    ("speech", 29.5, 135.6, {}),                        # Bane's monologue and the beating
    ("lift", 135.6, 137.7, {}),                         # "I will simply—"
    ("slam", 137.7, 138.45, {"speed": 0.4, "audio": "mute"}),
    ("knee", 138.45, 139.9, {"fx": "hit"}),
    ("scream", 139.9, 141.6, {}),
    ("fall", 141.6, 165.0, {}),                         # "...break you", thrown, the cave burns
    ("aftermath", 165.0, 231.5, {}),                    # the family, the PA, the drop, Bane lands
    ("gotham", 231.5, 258.0, {}),                       # the crowd, Batman in the light, Gordon
    ("signal", 258.0, 267.5, {"hold": 6.0}),            # the signal fades; end card
]

SHORT = [
    ("hook", 139.9, 141.4, {}),                         # the scream, cold
    ("lifted", 136.2, 137.7, {"audio": "bed"}),
    ("beaten1", 63.0, 68.0, {"audio": "bed"}),          # bloodied, on his knees
    ("beaten2", 93.0, 98.0, {"audio": "bed"}),          # the face
    ("bane", 123.65, 135.6, {}),                        # "I could kill you..." to "simply—"
    ("lift", 135.6, 137.7, {}),
    ("slam", 137.7, 138.45, {"speed": 0.4, "audio": "mute"}),
    ("knee", 138.45, 139.9, {"fx": "hit"}),
    ("scream", 139.9, 141.6, {}),
    ("fall", 141.6, 148.6, {"text": ("BROKEN.", 1.5)}),  # slides off; "...break you"
    ("thrown", 150.0, 153.4, {"audio": "bed"}),
    ("drop", 204.0, 206.4, {"audio": "bed", "cx": 0.45}),
    ("spotlight", 248.0, 250.6, {"audio": "bed"}),
    ("gordon", 250.6, 256.4, {}),                       # "Good God..." over Batman in the headlights
    ("end", 264.5, 267.5, {"audio": "bed", "hold": 2.3}),
]

# Narration: (id, text, segment, offset into that segment). Lines are placed
# only where the scene has no dialogue, so captions never collide.
LONG_LINES = [
    ("open", "Every Batman story ends the same way. He gets back up. This is the one where he doesn't.",
     "title", 0.2),
    ("cave", "Knightfall. Bane has spent months breaking Batman without laying a hand on him. He blew open Arkham, "
             "let every lunatic Batman ever caught loose on Gotham, and watched him run himself into the ground "
             "rounding them up. Now Bruce is limping home to the one place he thinks is safe. Bane is already there.",
     "cave", 4.6),
    ("floor", "No last punch. No escape. For the first time in his life, Bruce Wayne can't get up. "
              "And Bane isn't finished with him.",
     "fall", 12.6),
    ("close", "Bane didn't want Batman dead. Dead men turn into legends. He wanted Gotham to watch its protector "
              "carried off broken, and to understand that nobody was coming. That's Knightfall. "
              "The full fight that led here is on the channel.",
     "signal", 0.4),
]

SHORT_LINES = [
    ("hook", "This is the exact moment Batman broke.", "lifted", 0.0),
    ("setup", "Bane didn't sneak up on him. He spent months running Batman into the ground, "
              "then walked into the Batcave to finish it.", "beaten1", 1.9),
    ("gotham", "Bane didn't kill him. He dropped him in the middle of Gotham, so the whole city could see "
               "what was left.", "thrown", 0.1),
    ("close", "Knightfall. Batman doesn't get back up from this one.", "end", 0.2),
]


# --- Source dialogue -------------------------------------------------------------


def cue_sheet(profile: str, segments: List[Dict], words: List[Dict], total: float,
              width: int, height: int) -> Dict:
    S = lambda name: seg_by_name(segments, name)
    knee = S("knee")["t0"]
    if profile == "long":
        overlays = [
            {"type": "title_card", "start": S("title")["t0"] + 0.15, "end": S("title")["t1"] + 1.4,
             "label": "DC ANIMATED · KNIGHTFALL PART 1 (2026)", "title": "The Night Batman Broke",
             "subtitle": "Bane vs. Batman — the Batcave", "color": ACCENT},
            {"type": "lower_third", "start": S("cave")["t0"] + 1.0, "end": S("cave")["t0"] + 6.5,
             "label": "KNIGHTFALL", "title": "Bruce Wayne", "subtitle": "Months of running down Arkham's escapees",
             "color": ACCENT},
            {"type": "lower_third", "start": S("speech")["t0"] + 0.8, "end": S("speech")["t0"] + 6.3,
             "label": "THE INTRUDER", "title": "Bane", "subtitle": "Venom-enhanced · knows exactly who Batman is",
             "color": ACCENT},
            {"type": "callout", "start": S("fall")["t0"] + 1.0, "end": S("fall")["t0"] + 7.0,
             "label": "THE BREAK", "title": "Over the knee", "subtitle": "Knightfall's defining image, 1993 → 2026",
             "color": ACCENT},
            {"type": "badge", "start": S("aftermath")["t0"] + 0.5, "end": S("aftermath")["t0"] + 6.0,
             "title": "GOTHAM · THAT NIGHT", "color": ACCENT},
            {"type": "title_card", "start": S("signal")["t1"] - 5.2, "end": total - 0.3,
             "label": "NEXT", "title": "The full fight is on the channel",
             "subtitle": "Knightfall Part 1 · Batman vs. Bane", "color": ACCENT},
            {"type": "progress_bar", "start": 0, "end": total, "color": ACCENT},
        ]
        sfx = [
            {"query": "heavy cinematic impact hit", "start": round(S("cold_open")["t0"] + 1.85, 2), "duration": 1.6, "gain_db": -8},
            {"query": "deep cinematic whoosh", "start": round(S("title")["t0"], 2), "duration": 1.2, "gain_db": -14},
            {"query": "cinematic riser tension", "start": round(S("slam")["t0"] - 2.0, 2), "duration": 2.4, "gain_db": -14},
            {"query": "heavy cinematic impact hit", "start": round(knee, 2), "duration": 1.6, "gain_db": -6},
        ]
        music = {"query": "dark brooding cinematic tension underscore", "gain_db": -30}
        captions = {"style": "clean", "position": "bottom", "words_per_caption": 7,
                    "font_name": "Montserrat Black", "active_color": ACCENT}
    else:
        overlays = [
            {"type": "badge", "start": S("lifted")["t0"], "end": S("beaten2")["t1"],
             "title": "KNIGHTFALL · 2026", "color": ACCENT},
            {"type": "title_card", "start": S("end")["t0"] + 0.4, "end": total - 0.2,
             "label": "KNIGHTFALL", "title": "Full scene on the channel",
             "subtitle": "Batman vs. Bane · Part 1", "color": ACCENT},
            {"type": "progress_bar", "start": 0, "end": total, "color": ACCENT},
        ]
        sfx = [
            {"query": "deep cinematic whoosh", "start": round(S("hook")["t1"], 2), "duration": 1.0, "gain_db": -12},
            {"query": "slow heartbeat", "start": round(S("lift")["t0"], 2), "duration": 3.5, "gain_db": -10},
            {"query": "heavy cinematic impact hit", "start": round(knee, 2), "duration": 1.6, "gain_db": -6},
            {"query": "deep cinematic whoosh", "start": round(S("thrown")["t0"], 2), "duration": 1.0, "gain_db": -14},
        ]
        music = {"query": "dark epic hybrid trailer", "gain_db": -20}
        captions = {"style": "highlight", "position": "bottom", "words_per_caption": 4,
                    "font_name": "Montserrat Black", "uppercase": True, "active_color": ACCENT}
    clamp_overlays(overlays, total)
    return {
        "preset": "gaming", "width": width, "height": height, "fps": FPS, "duration": round(total, 3),
        "font_name": "Montserrat Black",
        "audio": {"provider": "epidemic", "music": music, "sfx": sfx},
        "captions": captions, "words": words, "overlays": overlays,
    }


# --- Build --------------------------------------------------------------------------------


def build(profile: str, finish: bool = True) -> Optional[Path]:
    width, height = (1920, 1080) if profile == "long" else (1080, 1920)
    plan, line_plan = (LONG, LONG_LINES) if profile == "long" else (SHORT, SHORT_LINES)
    work = OUTPUT_DIR / "work" / profile
    work.mkdir(parents=True, exist_ok=True)

    scene = words_from_lines(DIALOGUE)
    segments = resolve(plan, SOURCE, FPS)
    total = segments[-1]["t1"]
    print(f"\n[Knightfall/{profile}] {len(segments)} segments, {total:.1f}s")
    for s in segments:
        src = "black" if s.get("black") else f"{s['src_in']:.2f}-{s['src_out']:.2f} x{s['speed']:g} {s['audio']}"
        print(f"    {s['t0']:6.2f} -> {s['t1']:6.2f}  {s['name']:<10} {src}")

    lines = place_lines(line_plan, segments, work, narrate_line)
    for take in lines:
        print(f"    narration '{take['id']}': {take['t0']:.2f} -> {take['t1']:.2f} ({take['duration']:.1f}s)")

    pieces = render_segments(segments, work, width, height, FPS, ACCENT)
    track = work / "track.mp4"
    concat(pieces, track)

    clean = OUTPUT_DIR / f"Knightfall_Broken_{profile}_clean.mp4"
    mix_narration(track, lines, clean, total)
    print(f"[Knightfall/{profile}] Clean edit: {clean}")

    words = timeline_words(segments, scene, lines)
    config = cue_sheet(profile, segments, words, total, width, height)
    config_path = OUTPUT_DIR / f"Knightfall_Broken_{profile}_graphics.json"
    config_path.write_text(json.dumps(config, indent=1, ensure_ascii=False), encoding="utf-8")
    (OUTPUT_DIR / f"Knightfall_Broken_{profile}_timeline.json").write_text(
        json.dumps({"segments": segments, "narration": [{k: v for k, v in l.items() if k != "words"} for l in lines]},
                   indent=1, ensure_ascii=False, default=str), encoding="utf-8")

    # Editable caption sidecar, compiled offline.
    compile_captions(config_path, work / "captions.ass", OUTPUT_DIR / f"Knightfall_Broken_{profile}.srt")
    if profile == "long":
        write_chapters(segments)
    if not finish:
        return None

    final = OUTPUT_DIR / ("Knightfall_Broken_1920x1080.mp4" if profile == "long"
                          else "Knightfall_Broken_Short_1080x1920.mp4")
    finish(config_path, clean, final, OUTPUT_DIR / f"Knightfall_Broken_{profile}_render_report.json")
    print(f"[Knightfall/{profile}] Finished: {final}")
    return final


def write_chapters(segments: List[Dict]) -> None:
    marks = [("cold_open", "The moment"), ("cave", "Limping home"), ("speech", "Bane's monologue"),
             ("lift", "The break"), ("fall", "Broken"), ("aftermath", "Gotham fends for itself"),
             ("gotham", "The city sees"), ("signal", "Knightfall")]
    lines = []
    for name, label in marks:
        t = int(seg_by_name(segments, name)["t0"])
        lines.append(f"{t // 60:02d}:{t % 60:02d} {label}")
    (OUTPUT_DIR / "chapters.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--profile", choices=["long", "short", "both"], default="both")
    parser.add_argument("--no-finish", action="store_true", help="Stop at the clean edit; skip graphics and Epidemic audio")
    args = parser.parse_args()
    if not SOURCE:
        print(f"Source not found under {GAMING_DIR}")
        return 1
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for profile in (["long", "short"] if args.profile == "both" else [args.profile]):
        build(profile, finish=not args.no_finish)
    return 0


if __name__ == "__main__":
    sys.exit(main())
