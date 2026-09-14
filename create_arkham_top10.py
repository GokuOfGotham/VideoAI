"""Top 10 beatings at the hands of Batman — Arkham Knight. Long form and short.

A countdown cut from the 4K "Arkham Knight (The Movie)" recording. Each entry
is data: who gets it, the source window, and two Cedar lines — the setup,
spoken over the opening of the scene with the game audio low, and the payoff
after the hit. The window is split at the point the setup take ends, so the
game's own audio comes up exactly when the narrator stops. The short is the
top three at pace behind a cold-open hook.

Timestamps were located from a full transcript of the recording's dialogue
plus a loudness map, then confirmed frame by frame.

    python create_arkham_top10.py                 # both cuts
    python create_arkham_top10.py --profile long --no-finish
"""

import argparse
import glob
import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Tuple

from dotenv import load_dotenv

from edit_tools import (clamp_overlays, compile_captions, concat, finish, mix_narration, place_lines,
                        render_segments, resolve, seg_by_name, timeline_words)
from narration_tools import narrate_line

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = PROJECT_ROOT / "output" / "Arkham_Top10_Beatings"
GAMING_DIR = os.getenv("GAMING_VIDEOS_DIR", os.path.join(os.getenv("MEDIA_ROOT", "M:/Videos"), "Gaming"))
SOURCE = next(iter(glob.glob(os.path.join(GAMING_DIR, "PlayStation 5", "Batman Arkham Knight", "*The Movie*.mp4"))), None)

FPS = 30
ACCENT = "#F3D340"
GAP = 0.4        # seconds between the setup take ending and the game audio coming up
PAYOFF_TAIL = 0.6  # the payoff take ends this long before the entry's window closes

def T(h, m, s):
    return h * 3600 + m * 60 + s


# Ranked worst-to-best (10 first). `windows` are the source spans played, in
# order; the setup line runs over the start of the first one with the game
# audio low. `hit` is the money moment (the cold open and the short cut to
# these); `short_window` is the span the short plays; `cx` centres the 9:16
# crop. Located from the dialogue transcript and confirmed on frames.
ENTRIES: List[Dict] = [
    {"rank": 10, "name": "The first thug of the night", "label": "Chinatown · \"Where's Scarecrow?\"",
     "windows": [(T(0, 12, 33), T(0, 13, 4))], "hit": T(0, 12, 47), "cx": 0.5,
     "setup": "Number ten. The first thug of the night. Batman has been back in Gotham for about five minutes, "
              "and this guy has already picked the wrong ledge to stand near.",
     "payoff": "\"Go to hell\" is a bold answer to give a man who is holding you over the drop."},
    {"rank": 9, "name": "Two-Face", "label": "The third bank · \"Tails, you lose\"",
     "windows": [(T(3, 48, 37), T(3, 49, 31))], "hit": T(3, 49, 17), "cx": 0.5,
     "setup": "Number nine. Two-Face. Three bank jobs in one night, and Harvey runs out of coin flips at the third one.",
     "payoff": "One glide, one landing, and the other half of his face gets a matching bruise."},
    {"rank": 8, "name": "Scarecrow's militia", "label": "The GCPD roof · the last safe building in Gotham",
     "windows": [(T(3, 21, 58), T(3, 22, 50))], "hit": T(3, 22, 10), "cx": 0.5,
     "setup": "Number eight. The GCPD roof. Scarecrow drops an entire infantry squad on the last safe building "
              "in Gotham, and Batman is the only thing between them and the door.",
     "payoff": "They came in as a squad. They leave as a pile."},
    {"rank": 7, "name": "Albert King", "label": "Panessa Studios · Gotham's heavyweight, Joker-infected",
     "windows": [(T(2, 5, 24), T(2, 6, 34))], "hit": T(2, 5, 40), "cx": 0.5,
     "setup": "Number seven. Albert King. The Joker's blood turned Gotham's heavyweight champion into a fan, "
              "and the fan wants a title fight.",
     "payoff": "It lasts about as long as his last title defence did."},
    {"rank": 6, "name": "The Arkham Knight's driver", "label": "The crash site · \"Please stop\"",
     "windows": [(T(1, 23, 8), T(1, 24, 26))], "hit": T(1, 23, 34), "cx": 0.5,
     "setup": "Number six. The Arkham Knight's driver. Batman needs one name, and this man has it.",
     "payoff": "\"Please stop\" is the moment you know Batman didn't."},
    {"rank": 5, "name": "The Penguin", "label": "The Iceberg Lounge · \"I'll break every bone in your body\"",
     "windows": [(T(1, 24, 32), T(1, 25, 18))], "hit": T(1, 24, 36), "cx": 0.5,
     "setup": "Number five. The Penguin. Cobblepot sold the militia their safe houses, and Batman comes through "
              "the wall of the Iceberg Lounge to discuss the invoice.",
     "payoff": "\"I'll break every bone in your body\" isn't a threat. It's an itinerary."},
    {"rank": 4, "name": "The Riddler", "label": "Pinkney Orphanage · out of the mech, by the collar",
     "windows": [(T(3, 50, 32), T(3, 50, 44)), (T(3, 51, 24), T(3, 51, 52))], "hit": T(3, 51, 43.5), "cx": 0.5,
     "setup": "Number four. The Riddler. After a full night of death traps and a giant robot suit, Edward Nygma "
              "finally gets what he wanted: Batman's undivided attention.",
     "payoff": "Dragged out of his own machine by the collar. The last word goes to Catwoman."},
    {"rank": 3, "name": "Scarecrow", "label": "Arkham Asylum · a full dose of his own formula",
     "windows": [(T(3, 45, 44), T(3, 46, 46))], "hit": T(3, 46, 10), "cx": 0.5,
     "setup": "Number three. Scarecrow. Crane has just unmasked Bruce Wayne on live television and pumped him "
              "full of fear toxin. Then Bruce stops being afraid.",
     "payoff": "A full syringe of Scarecrow's own formula, straight into Scarecrow. He never comes back from it."},
    {"rank": 2, "name": "Jason Todd", "label": "The Arkham Knight · the Robin he thought was dead",
     "windows": [(T(3, 3, 41), T(3, 4, 2)), (T(3, 9, 8), T(3, 9, 34))], "hit": T(3, 9, 26), "cx": 0.5,
     "setup": "Number two. The Arkham Knight. Batman rips the helmet off the man who has hunted him all night, "
              "and finds Jason Todd. The Robin he thought the Joker killed.",
     "payoff": "Every punch after that is Bruce hitting his own worst failure in the face."},
    {"rank": 1, "name": "The Joker", "label": "Inside Batman's head · the one rule",
     "windows": [(T(3, 30, 5), T(3, 30, 53))], "hit": T(3, 30, 28.3), "cx": 0.5, "payoff_after": True,
     "setup": "Number one. The Joker. Or the version of him living inside Batman's head. He has spent the whole "
              "night telling Bruce he would snap eventually. This is where he finds out.",
     "payoff": "It's a hallucination. But the hands were real, and so was the choice. "
               "The Joker finally got the one thing he ever wanted: proof that Batman could."},
]

for _e in ENTRIES:
    _e["window"] = _e["windows"][0]
# The short plays the top three at pace.
_SHORT = {3: ((T(3, 46, 4), T(3, 46, 22)), "Number three. Scarecrow gets a full dose of his own toxin."),
          2: ((T(3, 9, 12), T(3, 9, 31)), "Number two. Jason Todd. His own Robin."),
          1: ((T(3, 30, 19), T(3, 30, 31.5)), "Number one. The Joker's neck.")}
for _e in ENTRIES:
    if _e["rank"] in _SHORT:
        _e["short_window"], _e["short_line"] = _SHORT[_e["rank"]]

HOOK_LINE = ("Batman doesn't kill. Everyone on this list probably wishes he had. "
             "These are the ten worst beatings he handed out in Arkham Knight.")
CLOSE_LINE = ("That's the ten. And if the Joker one got to you, the night Bane broke Batman for real "
              "is already on the channel.")
SHORT_HOOK_LINE = "Batman doesn't kill. He does this instead."
SHORT_CLOSE_LINE = "The full top ten is on the channel."


# --- Plans -------------------------------------------------------------------------


def take_lengths(work: Path, lines: List[Tuple[str, str]]) -> Dict[str, float]:
    """Records (or reuses) the takes and returns each one's length by id."""
    return {lid: narrate_line(text, work / f"line_{lid}.wav")["duration"] for lid, text in lines}


def long_plans(work: Path):
    ids = [("hook", HOOK_LINE), ("close", CLOSE_LINE)]
    for e in ENTRIES:
        ids += [(f"setup{e['rank']}", e["setup"]), (f"payoff{e['rank']}", e["payoff"])]
    length = take_lengths(work, ids)

    plan, lines = [], []
    # Cold open: the three biggest hits, fast, under the hook. The last hit
    # runs on until the hook line has finished, so there is never dead black.
    top3 = [x for x in ENTRIES if x["rank"] <= 3]
    for i, e in enumerate(top3[:-1]):
        plan.append((f"open{i}", e["hit"] - 1.2, e["hit"] + 1.3, {"audio": "bed", "cx": e.get("cx", 0.5)}))
    e = top3[-1]
    tail = max(1.3, length["hook"] + 0.5 - 2 * 2.5 - 1.2)
    plan.append((f"open{len(top3) - 1}", e["hit"] - 1.2, e["hit"] + tail, {"audio": "bed", "cx": e.get("cx", 0.5)}))
    lines.append(("hook", HOOK_LINE, "open0", 0.2))
    # The title card sits on footage, not black: Batman walking up to the crash site in the rain.
    plan.append(("title", T(1, 22, 54), T(1, 22, 54) + 3.6, {"audio": "bed"}))

    for e in ENTRIES:
        r = e["rank"]
        cx = e.get("cx", 0.5)
        (a, b), rest = e["windows"][0], e["windows"][1:]
        split = a + length[f"setup{r}"] + GAP
        if b < split + 1.0:
            b = split + 1.0  # the setup outran the first window; let it run on
        plan.append((f"e{r}_setup", a, split, {"audio": "bed", "cx": cx, "text": (f"#{r}", 1.7), "text_size": 0.3}))
        plan.append((f"e{r}_full", split, b, {"cx": cx}))
        last = f"e{r}_full"
        for k, (c, d) in enumerate(rest):
            last = f"e{r}_more{k}"
            plan.append((last, c, d, {"cx": cx}))
        # The payoff ends just before the entry's last window closes; a window
        # too short for it is extended rather than talking over the next entry.
        name, c, d, opts = plan[-1]
        begin = c if last != f"e{r}_full" else split
        if e.get("payoff_after"):
            # Freeze the last frame and speak over the hold, after the scene's own last line.
            hold = length[f"payoff{r}"] + 1.2
            plan[-1] = (name, c, d, {**opts, "hold": hold})
            start_in_last = (d - begin) + 0.4
        else:
            need = begin + length[f"payoff{r}"] + PAYOFF_TAIL + 1.0
            if d < need:
                plan[-1] = (name, c, need, opts)
                d = need
            start_in_last = (d - begin) - length[f"payoff{r}"] - PAYOFF_TAIL
        lines.append((f"setup{r}", e["setup"], f"e{r}_setup", 0.25))
        lines.append((f"payoff{r}", e["payoff"], last, round(start_in_last, 3)))

    # Outro on footage as well: Batman over Gotham, then the end card.
    plan.append(("outro", T(0, 6, 58), T(0, 6, 58) + length["close"] + 4.0, {"audio": "bed"}))
    lines.append(("close", CLOSE_LINE, "outro", 0.5))
    return plan, lines


def short_plans(work: Path):
    top = sorted([e for e in ENTRIES if e["rank"] <= 3], key=lambda e: -e["rank"])
    ids = [("shook", SHORT_HOOK_LINE), ("sclose", SHORT_CLOSE_LINE)]
    ids += [(f"s{e['rank']}", e["short_line"]) for e in top]
    length = take_lengths(work, ids)

    one = next(e for e in ENTRIES if e["rank"] == 1)
    plan = [("shook_hit", one["hit"] - 0.6, one["hit"] + 0.9, {"cx": one.get("cx", 0.5)})]
    # The hook line rides on Bruce's grip on Crane, not the dark frames after the snap.
    plan.append(("shook_bed", T(3, 46, 12), T(3, 46, 12) + length["shook"] + GAP, {"audio": "bed", "cx": 0.5}))
    lines = [("shook", SHORT_HOOK_LINE, "shook_bed", 0.0)]
    for e in top:
        r = e["rank"]
        a, b = e["short_window"]
        split = a + length[f"s{r}"] + GAP
        plan.append((f"s{r}_setup", a, split, {"audio": "bed", "cx": e.get("cx", 0.5),
                                                 "text": (f"#{r}", 1.4), "text_size": 0.3}))
        plan.append((f"s{r}_full", split, b, {"cx": e.get("cx", 0.5)}))
        lines.append((f"s{r}", e["short_line"], f"s{r}_setup", 0.2))
    # End card on footage: Batman walking up to the crash site in the rain.
    plan.append(("send", T(1, 22, 55), T(1, 22, 55) + length["sclose"] + 1.6, {"audio": "bed", "cx": 0.5}))
    lines.append(("sclose", SHORT_CLOSE_LINE, "send", 0.3))
    return plan, lines


# --- Graphics -------------------------------------------------------------------------


def cue_sheet(profile: str, segments: List[Dict], words: List[Dict], total: float,
              width: int, height: int) -> Dict:
    S = lambda name: seg_by_name(segments, name)
    overlays, sfx = [], []
    if profile == "long":
        overlays.append({"type": "title_card", "start": S("title")["t0"] + 0.15, "end": S("title")["t1"] - 0.1,
                         "label": "BATMAN: ARKHAM KNIGHT", "title": "Top 10 Beatings at the Hands of Batman",
                         "subtitle": "One rule. No mercy.", "color": ACCENT})
        sfx.append({"query": "deep cinematic whoosh", "start": round(S("title")["t0"], 2), "duration": 1.2, "gain_db": -14})
        for e in ENTRIES:
            r = e["rank"]
            s = S(f"e{r}_setup")
            overlays.append({"type": "lower_third", "start": round(s["t0"] + 1.9, 2), "end": round(s["t0"] + 7.4, 2),
                             "label": f"NUMBER {r}", "title": e["name"], "subtitle": e["label"], "color": ACCENT})
            sfx.append({"query": "heavy cinematic impact hit", "start": round(s["t0"], 2), "duration": 1.2, "gain_db": -12})
        overlays.append({"type": "title_card", "start": S("outro")["t0"] + 0.3, "end": total - 0.3,
                         "label": "NEXT", "title": "The night Batman broke", "subtitle": "Knightfall — on the channel",
                         "color": ACCENT})
        music = {"query": "dark heroic cinematic hybrid underscore", "gain_db": -28}
        captions = {"style": "clean", "position": "bottom", "words_per_caption": 7,
                    "font_name": "Montserrat Black", "active_color": ACCENT}
    else:
        for e in sorted([x for x in ENTRIES if x["rank"] <= 3], key=lambda x: -x["rank"]):
            r = e["rank"]
            s = S(f"s{r}_setup")
            overlays.append({"type": "badge", "start": round(s["t0"] + 1.5, 2), "end": round(S(f"s{r}_full")["t1"], 2),
                             "title": f"#{r} · {e['name'].upper()}", "color": ACCENT})
            sfx.append({"query": "heavy cinematic impact hit", "start": round(s["t0"], 2), "duration": 1.2, "gain_db": -15})
        sfx.append({"query": "deep cinematic whoosh", "start": round(S("shook_bed")["t0"], 2), "duration": 1.0, "gain_db": -14})
        overlays.append({"type": "title_card", "start": S("send")["t0"] + 0.3, "end": total - 0.2,
                         "label": "ARKHAM KNIGHT", "title": "Full top 10 on the channel",
                         "subtitle": "Beatings at the hands of Batman", "color": ACCENT})
        music = {"query": "dark epic hybrid trailer", "gain_db": -24}
        captions = {"style": "highlight", "position": "bottom", "words_per_caption": 4,
                    "font_name": "Montserrat Black", "uppercase": True, "active_color": ACCENT}
    overlays.append({"type": "progress_bar", "start": 0, "end": total, "color": ACCENT})
    clamp_overlays(overlays, total)
    return {
        "preset": "gaming", "width": width, "height": height, "fps": FPS, "duration": round(total, 3),
        "font_name": "Montserrat Black",
        "audio": {"provider": "epidemic", "music": music, "sfx": sfx},
        "captions": captions, "words": words, "overlays": overlays,
    }


# --- Build ------------------------------------------------------------------------------


def build(profile: str, do_finish: bool = True):
    width, height = (1920, 1080) if profile == "long" else (1080, 1920)
    work = OUTPUT_DIR / "work" / profile
    work.mkdir(parents=True, exist_ok=True)

    plan, line_plan = long_plans(work) if profile == "long" else short_plans(work)
    segments = resolve(plan, SOURCE, FPS)
    total = segments[-1]["t1"]
    print(f"\n[Top10/{profile}] {len(segments)} segments, {total / 60:.1f} min")
    lines = place_lines(line_plan, segments, work, narrate_line)
    for take in lines:
        print(f"    '{take['id']}': {take['t0']:.2f} -> {take['t1']:.2f} ({take['duration']:.1f}s)")

    pieces = render_segments(segments, work, width, height, FPS, ACCENT, log=lambda m: print(m))
    track = work / "track.mp4"
    concat(pieces, track)
    clean = OUTPUT_DIR / f"Arkham_Top10_{profile}_clean.mp4"
    mix_narration(track, lines, clean, total)
    print(f"[Top10/{profile}] Clean edit: {clean}")

    words = timeline_words(segments, [], lines)
    config = cue_sheet(profile, segments, words, total, width, height)
    config_path = OUTPUT_DIR / f"Arkham_Top10_{profile}_graphics.json"
    config_path.write_text(json.dumps(config, indent=1, ensure_ascii=False), encoding="utf-8")
    (OUTPUT_DIR / f"Arkham_Top10_{profile}_timeline.json").write_text(
        json.dumps({"segments": segments, "narration": [{k: v for k, v in l.items() if k != "words"} for l in lines]},
                   indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    compile_captions(config_path, work / "captions.ass", OUTPUT_DIR / f"Arkham_Top10_{profile}.srt")
    if profile == "long":
        marks = [("open0", "The hits"), ("title", "Top 10")] + [(f"e{e['rank']}_setup", f"#{e['rank']} {e['name']}") for e in ENTRIES]
        (OUTPUT_DIR / "chapters.txt").write_text(
            "".join(f"{int(seg_by_name(segments, n)['t0']) // 60:02d}:{int(seg_by_name(segments, n)['t0']) % 60:02d} {label}\n"
                    for n, label in marks), encoding="utf-8")
    if not do_finish:
        return
    final = OUTPUT_DIR / ("Arkham_Top10_Beatings_1920x1080.mp4" if profile == "long" else "Arkham_Top10_Beatings_Short_1080x1920.mp4")
    finish(config_path, clean, final, OUTPUT_DIR / f"Arkham_Top10_{profile}_render_report.json")
    print(f"[Top10/{profile}] Finished: {final}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--profile", choices=["long", "short", "both"], default="both")
    parser.add_argument("--no-finish", action="store_true", help="Stop at the clean edit; skip graphics and Epidemic audio")
    args = parser.parse_args()
    if not SOURCE:
        print(f"Source not found under {GAMING_DIR}")
        return 1
    if not ENTRIES:
        print("ENTRIES is empty; index the recording and fill it in first.")
        return 1
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for profile in (["long", "short"] if args.profile == "both" else [args.profile]):
        build(profile, do_finish=not args.no_finish)
    return 0


if __name__ == "__main__":
    sys.exit(main())
