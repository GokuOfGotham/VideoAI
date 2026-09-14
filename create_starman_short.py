"""Starman: the Falcon Heavy demo flight that put a Tesla Roadster in space.

A vertical short built from SpaceX's own "Falcon Heavy & Starman" recap.
Narration is OpenAI TTS (Onyx — recorded before the Cedar preset in AGENTS.md
became the default); word timings come from OpenAI's transcription so the
captions track the finished voice. Each beat of the script is anchored to the
word it ends on, and its shots are cut and cropped to 9:16 to fill exactly
that span. The clean edit is then finished through ``graphics_tool.py`` for
the space-preset overlays, captions, and the required Epidemic soundtrack.

    python create_starman_short.py            # full build
    python create_starman_short.py --no-finish  # stop at the clean edit
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional

from dotenv import load_dotenv

from narration_tools import locate, restore_punctuation, sanitise, transcribe_words
from voice_synthesizer import synthesize_narration, get_audio_duration

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = PROJECT_ROOT / "output" / "Starman"
WORK_DIR = OUTPUT_DIR / "work"
MATERIALS = PROJECT_ROOT / "assets" / "materials" / "starman"
FONTS_DIR = PROJECT_ROOT / "assets" / "fonts"

# SpaceX, "Falcon Heavy & Starman" (youtube.com/watch?v=A0FZIwabctw), 1080p.
RECAP = MATERIALS / "src_A0FZIwabctw.mp4"

WIDTH, HEIGHT, FPS = 1080, 1920, 30
TAIL = 1.2  # seconds the last shot holds after the narration ends

NARRATION = (
    "February sixth, twenty-eighteen. Kennedy Space Center, Florida. "
    "The Falcon Heavy — the most powerful rocket in the world — is about to fly for the first time. "
    "Twenty-seven engines. Five million pounds of thrust. "
    "And a test payload nobody saw coming: Elon Musk's own cherry-red Tesla Roadster... "
    "with a mannequin named Starman at the wheel. "
    "Three. Two. One. Liftoff. "
    "Two and a half minutes later, the twin side boosters separate — and fly themselves home, "
    "landing side by side, at the exact same moment. "
    "The center core wasn't so lucky. It ran out of igniter fluid... "
    "and hit the Atlantic at three hundred miles an hour. "
    "But the Roadster kept going. Six hours through the Van Allen belts, "
    "then one final burn — out past the orbit of Mars. "
    "On the dashboard: Don't Panic. On the stereo: David Bowie's Space Oddity, on loop. "
    "Starman is still out there — circling the Sun, and expected to keep going for millions of years."
)

# Open-ocean aerial for the centre core's splashdown, from the CC b-roll tier
# (the recap only has a phone clip of the sea). Resolved when the shots are cut.
OCEAN = "broll:deep blue open sea rough waves aerial"

# Each beat runs until the narration reaches `ends_after` (a distinctive last
# word, matched in order). Shots are (source, in, out, options): `cx` is the
# horizontal centre of the 9:16 crop as a fraction of the frame; `fit` keeps
# the whole frame over a blurred backdrop instead of cropping; `speed` below
# 1.0 slows a shot, which suits the drifting space footage better than a hold.
BEATS = [
    {"ends_after": "Florida", "shots": [
        (RECAP, 28.32, 30.36, {"cx": 0.45}),      # VAB, NASA meatball
        (RECAP, 37.33, 44.09, {"cx": 0.37}),      # pad 39A, wide
    ]},
    {"ends_after": "time", "shots": [
        (RECAP, 32.37, 36.37, {"cx": 0.55}),      # Falcon Heavy on the pad at dusk
        (RECAP, 16.39, 24.36, {"cx": 0.50}),      # the hangar at night
    ]},
    {"ends_after": "thrust", "shots": [
        (RECAP, 44.09, 46.13, {"cx": 0.42}),      # vehicle close-up, launch-day timestamp
        (RECAP, 26.32, 28.32, {"cx": 0.50}),      # rolling out of the hangar at night
    ]},
    {"ends_after": "wheel", "shots": [
        (RECAP, 6.42, 7.97, {"cx": 0.55}),        # pulling the cover off
        (RECAP, 7.97, 9.43, {"cx": 0.60}),        # the Roadster on the lift
        (RECAP, 14.26, 15.72, {"cx": 0.50}),      # Roadster close-up
        (RECAP, 84.67, 86.54, {"cx": 0.45}),      # Starman in the driver's seat
    ]},
    {"ends_after": "One", "shots": [
        (RECAP, 46.13, 48.30, {"cx": 0.45}),      # ignition under the countdown
    ]},
    {"ends_after": "later", "shots": [       # liftoff runs under "two and a half minutes later"
        (RECAP, 48.30, 50.47, {"cx": 0.45}),      # liftoff
        (RECAP, 53.14, 54.18, {"cx": 0.55}),      # climbing
    ]},
    {"ends_after": "moment", "shots": [
        (RECAP, 54.18, 57.97, {"cx": 0.50}),      # onboard: side booster separation
        (RECAP, 97.85, 100.73, {"fit": True}),    # twin landing, side by side
    ]},
    {"ends_after": "hour", "shots": [
        (RECAP, 90.17, 92.18, {"cx": 0.50}),      # booster, landing burn
        (RECAP, 100.73, 102.81, {"cx": 0.50}),    # descent camera through the haze
        (OCEAN, 0.0, 3.0, {"vertical": True}),    # the Atlantic
    ]},
    {"ends_after": "Mars", "shots": [
        (RECAP, 70.07, 71.36, {"cx": 0.38}),      # second stage burning over Earth
        (RECAP, 79.00, 82.79, {"cx": 0.50, "speed": 0.6}),  # Starman, Earth behind
    ]},
    {"ends_after": "loop", "shots": [
        (RECAP, 82.79, 84.67, {"cx": 0.50}),      # from inside the Roadster
        (RECAP, 108.27, 112.40, {"cx": 0.42}),    # "Made on Earth by humans"
    ]},
    {"ends_after": "years", "shots": [
        (RECAP, 104.35, 108.27, {"cx": 0.52, "speed": 0.6}),  # crescent Earth, Starman drifting
    ]},
]


# --- Narration ---------------------------------------------------------------


def narrate() -> Dict:
    cached = WORK_DIR / "narration.json"
    if cached.exists():
        data = json.loads(cached.read_text(encoding="utf-8"))
        if Path(data["audio"]).exists():
            data["words"] = sanitise(data["words"])
            print(f"[Starman] Reusing narration ({data['duration']:.1f}s, {len(data['words'])} words)")
            return data

    audio, duration, _ = synthesize_narration(
        NARRATION, output_filename="starman_narration.mp3",
        provider="openai", voice="onyx", word_timestamps=False,
    )
    words = transcribe_words(audio)["words"]
    if not words:
        raise RuntimeError("No word timings; OPENAI_API_KEY is needed for the transcription.")
    words = restore_punctuation(words, NARRATION)
    data = {"audio": audio, "duration": duration, "words": words}
    cached.write_text(json.dumps(data, indent=1), encoding="utf-8")
    print(f"[Starman] Narration {duration:.1f}s, {len(words)} timed words")
    return data


def beat_spans(words: List[Dict], duration: float) -> List[List[float]]:
    """[start, end] of each beat, found by walking the transcript in order."""
    spans, cursor, i = [], 0.0, 0
    for beat in BEATS[:-1]:
        i = locate(words, beat["ends_after"], i)
        end = words[i]["end"] + 0.15  # cut just after the word lands
        spans.append([cursor, end])
        cursor = end
        i += 1
    spans.append([cursor, duration + TAIL])
    return spans


# --- Shots --------------------------------------------------------------------


def _shot_filter(opts: Dict) -> str:
    pre = ""
    if "crop" in opts:
        x, y, w, h = opts["crop"]
        pre = f"crop={w}:{h}:{x}:{y},"
    speed = float(opts.get("speed", 1.0))
    if speed != 1.0:
        pre += f"setpts=PTS/{speed},"
    if opts.get("vertical"):  # already a 1080x1920 clip from the b-roll tier
        return f"{pre}scale={WIDTH}:{HEIGHT},setsar=1,fps={FPS}"
    if opts.get("fit"):
        return (
            f"{pre}split[bg][fg];"
            f"[bg]scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,"
            f"crop={WIDTH}:{HEIGHT},gblur=sigma=45,eq=brightness=-0.2[bgb];"
            f"[fg]scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=decrease[fgs];"
            f"[bgb][fgs]overlay=(W-w)/2:(H-h)/2,setsar=1,fps={FPS}"
        )
    cx = float(opts.get("cx", 0.5))
    # A full-height 9:16 window, centred on the subject and kept inside the frame.
    return (
        f"{pre}crop=w=ih*9/16:h=ih:x='min(max(iw*{cx}-ih*9/32,0),iw-ih*9/16)':y=0,"
        f"scale={WIDTH}:{HEIGHT}:flags=lanczos,setsar=1,fps={FPS}"
    )


def _resolve(src) -> Path:
    """A shot's file on disk; `broll:` sources come from the YouTube CC tier."""
    if isinstance(src, str) and src.startswith("broll:"):
        from youtube_broll import fetch_broll_clip
        clip = fetch_broll_clip(src[len("broll:"):], target_duration=3.0)
        if not clip:
            raise RuntimeError(f"No b-roll for '{src}'")
        return Path(clip.path)
    return Path(src)


def _allocate(shots: List, span: float) -> List[float]:
    """Splits a beat across its shots, no shot longer than its (slowed) source."""
    avail = [max(0.3, (out - start) / float(opts.get("speed", 1.0))) for _, start, out, opts in shots]
    share = [span / len(shots)] * len(shots)
    for _ in range(len(shots)):
        spare = sum(max(0.0, s - a) for s, a in zip(share, avail))
        share = [min(s, a) for s, a in zip(share, avail)]
        room = [i for i, (s, a) in enumerate(zip(share, avail)) if a - s > 1e-3]
        if spare <= 1e-3 or not room:
            break
        for i in room:
            share[i] += spare / len(room)
    return share


def cut_shots(spans: List[List[float]]) -> List[Path]:
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    pieces = []
    n = 0
    for beat, (start, end) in zip(BEATS, spans):
        lengths = _allocate(beat["shots"], end - start)
        for k, ((src, s_in, s_out, opts), length) in enumerate(zip(beat["shots"], lengths)):
            dest = WORK_DIR / f"shot_{n:02d}.mp4"
            n += 1
            # The last shot of a beat absorbs any shortfall by holding its
            # final frame, so the edit always lines up with the narration.
            last = k == len(beat["shots"]) - 1
            hold = max(0.0, (end - start) - sum(lengths)) if last else 0.0
            vf = _shot_filter(opts)
            if hold > 0.02:
                vf += f",tpad=stop_mode=clone:stop_duration={hold:.3f}"
            read = length * float(opts.get("speed", 1.0))  # source seconds to cover `length`
            cmd = [
                "ffmpeg", "-y", "-v", "error",
                "-ss", f"{s_in:.3f}", "-t", f"{read:.3f}", "-i", str(_resolve(src)),
                "-filter_complex" if "[" in vf else "-vf", vf,
                "-an", "-c:v", "libx264", "-preset", "fast", "-crf", "17",
                "-pix_fmt", "yuv420p", "-r", str(FPS), str(dest),
            ]
            subprocess.run(cmd, check=True)
            pieces.append(dest)
            print(f"[Starman]   shot {dest.name}: {Path(str(src)).name} {s_in:.1f}s +{length:.2f}s"
                  + (f" (+{hold:.2f}s hold)" if hold > 0.02 else ""))
    return pieces


def assemble(pieces: List[Path], narration: Dict, total: float) -> Path:
    listing = WORK_DIR / "concat.txt"
    listing.write_text("".join(f"file '{p.resolve().as_posix()}'\n" for p in pieces), encoding="utf-8")
    clean = OUTPUT_DIR / "starman_clean.mp4"
    fade = 0.8
    subprocess.run([
        "ffmpeg", "-y", "-v", "error",
        "-f", "concat", "-safe", "0", "-i", str(listing),
        "-i", narration["audio"],
        "-filter_complex",
        f"[0:v]fade=t=in:st=0:d=0.5,fade=t=out:st={total - fade:.3f}:d={fade}[v];"
        f"[1:a]apad,atrim=0:{total:.3f},afade=t=out:st={total - fade:.3f}:d={fade}[a]",
        "-map", "[v]", "-map", "[a]",
        "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-t", f"{total:.3f}", "-movflags", "+faststart",
        str(clean),
    ], check=True)
    return clean


# --- Graphics -----------------------------------------------------------------


def cue_sheet(narration: Dict, spans: List[List[float]], total: float) -> Path:
    b = {beat["ends_after"]: span for beat, span in zip(BEATS, spans)}
    words = narration["words"]
    liftoff = words[locate(words, "Liftoff")]["start"]
    config = {
        "preset": "space",
        "width": WIDTH, "height": HEIGHT, "fps": FPS, "duration": round(total, 3),
        "font_name": "Montserrat Black",
        "audio": {
            "provider": "epidemic",
            "music": {"query": "cinematic ambient space orchestral", "gain_db": -22},
            "sfx": [
                {"query": "rocket launch rumble", "start": round(liftoff, 2), "duration": 3.5, "gain_db": -10},
                {"query": "deep cinematic whoosh", "start": round(b["later"][1], 2), "duration": 1.2, "gain_db": -14},
                {"query": "deep cinematic whoosh", "start": round(b["hour"][1], 2), "duration": 1.2, "gain_db": -14},
            ],
        },
        "captions": {
            "style": "highlight", "position": "bottom", "words_per_caption": 4,
            "font_name": "Montserrat Black", "uppercase": True,
        },
        "words": narration["words"],
        "overlays": [
            {"type": "lower_third", "start": 0.3, "end": round(b["Florida"][1], 2),
             "label": "MISSION BRIEF", "title": "Falcon Heavy Demo Flight",
             "subtitle": "Kennedy Space Center · LC-39A · Feb 6, 2018"},
            {"type": "callout", "start": round(b["thrust"][0], 2), "end": round(b["thrust"][1], 2),
             "label": "FALCON HEAVY", "title": "27 Merlin engines",
             "subtitle": "5 million lbf of thrust at liftoff"},
            {"type": "callout", "start": round(b["wheel"][0], 2), "end": round(b["wheel"][1], 2),
             "label": "TEST PAYLOAD", "title": "2008 Tesla Roadster",
             "subtitle": "Driver: Starman, in a SpaceX pressure suit"},
            {"type": "badge", "start": round(b["moment"][0] + 1.5, 2), "end": round(b["moment"][1], 2),
             "title": "TWIN LANDING · LZ-1 & LZ-2"},
            {"type": "callout", "start": round(b["hour"][0], 2), "end": round(b["hour"][1], 2),
             "label": "CENTER CORE", "title": "Missed the droneship",
             "subtitle": "Only 1 of 3 engines relit · ~300 mph into the water"},
            {"type": "callout", "start": round(b["Mars"][0], 2), "end": round(b["Mars"][1], 2),
             "label": "ORBIT", "title": "Heliocentric, past Mars",
             "subtitle": "Aphelion 1.66 AU · period about 1.5 years"},
            {"type": "callout", "start": round(b["loop"][0], 2), "end": round(b["loop"][1], 2),
             "label": "ON BOARD", "title": "Don't Panic",
             "subtitle": "Space Oddity on loop · a towel and a Hitchhiker's Guide"},
            {"type": "callout", "start": round(b["years"][0], 2), "end": round(total - 0.6, 2),
             "label": "STILL OUT THERE", "title": "Orbiting the Sun",
             "subtitle": "Closest pass of Mars so far: October 2020"},
            {"type": "progress_bar", "start": 0, "end": round(total, 3)},
        ],
    }
    path = OUTPUT_DIR / "starman_graphics.json"
    path.write_text(json.dumps(config, indent=1, ensure_ascii=False), encoding="utf-8")
    return path


def finish(clean: Path, config: Path) -> Path:
    final = OUTPUT_DIR / "Starman_Falcon_Heavy_Short.mp4"
    subprocess.run([
        sys.executable, str(PROJECT_ROOT / "graphics_tool.py"), "render",
        "--config", str(config), "--input", str(clean), "--output", str(final),
        "--encoder", "auto", "--fonts-dir", str(FONTS_DIR), "--overwrite",
    ], check=True)
    return final


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--no-finish", action="store_true",
                        help="Stop after the clean edit; skip graphics and Epidemic audio")
    args = parser.parse_args()

    if not RECAP.exists():
        print(f"Missing source {RECAP}. Download it first:\n"
              f"  yt-dlp -f \"bv*[height<=1080]\" -o \"{RECAP}\" https://www.youtube.com/watch?v=A0FZIwabctw")
        return 1
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    WORK_DIR.mkdir(parents=True, exist_ok=True)

    narration = narrate()
    total = narration["duration"] + TAIL
    spans = beat_spans(narration["words"], narration["duration"])
    for beat, (s, e) in zip(BEATS, spans):
        print(f"[Starman] beat ends '{beat['ends_after']}': {s:6.2f} -> {e:6.2f}  ({e - s:.2f}s)")

    pieces = cut_shots(spans)
    clean = assemble(pieces, narration, total)
    print(f"[Starman] Clean edit: {clean} ({get_audio_duration(str(clean)):.2f}s)")

    config = cue_sheet(narration, spans, total)
    print(f"[Starman] Cue sheet: {config}")
    if args.no_finish:
        return 0

    final = finish(clean, config)
    print(f"\n[Starman] Finished: {final}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
