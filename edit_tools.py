"""Segment-based editing engine shared by the ``create_*`` recipes.

A recipe describes an edit as a list of segments — (name, src_in, src_out,
options) cut from a source file, or black — plus narration lines placed at a
segment and offset. This module turns that into a clean edit: it renders each
segment (speed, 9:16 crop, impact shake, big centred word, freeze holds),
concatenates them, levels the source audio and ducks it under the narration,
and produces the timed word list the graphics tool captions from. Rendered
segments are cached by content, so re-running a recipe only re-encodes what
changed. The finishing pass (captions, overlays, Epidemic audio) is
``graphics_tool.py``; ``finish()`` wraps it.
"""

import functools
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent
FONTS_DIR = PROJECT_ROOT / "assets" / "fonts"
BIG_FONT = "assets/fonts/Montserrat-Black.ttf"  # relative: drawtext runs with cwd=PROJECT_ROOT


@functools.lru_cache(maxsize=None)
def is_hdr(src: str) -> bool:
    """True for PQ/HLG sources, which need tone-mapping to look right in SDR.

    Console captures are often HDR10; scaled without tone-mapping they come
    out flat and grey, and the graphics finisher refuses them outright.
    """
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=color_transfer", "-of", "default=nw=1:nk=1", src],
                         capture_output=True, text=True).stdout.strip().lower()
    return out in ("smpte2084", "arib-std-b67")


# --- Timeline -----------------------------------------------------------------------


def resolve(plan: List, source, fps: int = 30) -> List[Dict]:
    """Segments with output-time positions.

    `plan` entries are (name, src_in, src_out, options). `src_in` None makes a
    black segment `src_out` seconds long. Options: `src` overrides `source`;
    `speed` < 1 slows; `audio` is "source" (kept, captioned), "bed" (kept low,
    uncaptioned) or "mute"; `fx` "hit" adds the impact shake and flash; `cx`
    centres a 9:16 crop; `text` (word, seconds) punches in a big word; `hold`
    freezes the last frame for that long.
    """
    out, t = [], 0.0
    for name, src_in, src_out, opts in plan:
        if src_in is None:
            length = float(src_out)
            seg = {"name": name, "black": True, "length": length, **opts}
        else:
            speed = float(opts.get("speed", 1.0))
            length = (src_out - src_in) / speed + float(opts.get("hold", 0.0))
            seg = {"name": name, "src": str(opts.get("src", source)), "src_in": float(src_in),
                   "src_out": float(src_out), "speed": speed, "audio": opts.get("audio", "source"),
                   "length": length, **{k: v for k, v in opts.items() if k != "src"}}
        seg["t0"], seg["t1"] = round(t, 3), round(t + length, 3)
        t += length
        out.append(seg)
    return out


def seg_by_name(segments: List[Dict], name: str) -> Dict:
    return next(s for s in segments if s["name"] == name)


def place_lines(line_plan: List, segments: List[Dict], work: Path, narrate) -> List[Dict]:
    """Records (or reuses) each narration take and places it on the timeline.

    `line_plan` entries are (id, text, segment_name, offset). Lines may not
    overlap; a recipe fixes that by moving a line or rewriting it, never by
    speeding the take up (AGENTS.md).
    """
    lines = []
    for lid, text, seg_name, offset in line_plan:
        take = narrate(text, work / f"line_{lid}.wav")
        take["id"] = lid
        take["t0"] = round(seg_by_name(segments, seg_name)["t0"] + offset, 3)
        take["t1"] = round(take["t0"] + take["duration"], 3)
        lines.append(take)
    for a, b in zip(lines, lines[1:]):
        if b["t0"] < a["t1"]:
            raise RuntimeError(f"Narration '{a['id']}' ends at {a['t1']:.2f} but '{b['id']}' starts at {b['t0']:.2f}")
    return lines


# --- Rendering ------------------------------------------------------------------------


def _atempo(speed: float) -> str:
    chain, s = [], speed
    while s < 0.5:
        chain.append("atempo=0.5"); s /= 0.5
    while s > 2.0:
        chain.append("atempo=2.0"); s /= 2.0
    chain.append(f"atempo={s:.4f}")
    return ",".join(chain)


def render_segment(seg: Dict, dest: Path, width: int, height: int, fps: int = 30,
                   accent: str = "#F3D340") -> None:
    vertical = height > width
    if seg.get("black"):
        subprocess.run([
            "ffmpeg", "-y", "-v", "error",
            "-f", "lavfi", "-i", f"color=c=black:s={width}x{height}:r={fps}:d={seg['length']:.3f}",
            "-f", "lavfi", "-i", f"anullsrc=r=48000:cl=stereo:d={seg['length']:.3f}",
            "-c:v", "libx264", "-preset", "fast", "-crf", "17", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k", "-shortest", str(dest),
        ], check=True)
        return

    speed, hold = seg["speed"], float(seg.get("hold", 0.0))
    read = seg["src_out"] - seg["src_in"]
    vf = []
    if speed != 1.0:
        vf.append(f"setpts=PTS/{speed}")
    if vertical:
        cx = float(seg.get("cx", 0.5))
        vf.append(f"crop=w=ih*9/16:h=ih:x='min(max(iw*{cx}-ih*9/32,0),iw-ih*9/16)':y=0")
    if is_hdr(seg["src"]):
        # HDR10 -> BT.709 SDR, scaled in linear light on the way (Hable curve
        # keeps the blacks; a plain scale leaves the picture washed out).
        vf.append(f"zscale=w={width}:h={height}:t=linear:npl=100:f=lanczos,format=gbrpf32le,"
                  "zscale=p=bt709,tonemap=tonemap=hable:desat=0,zscale=t=bt709:m=bt709:r=tv,"
                  f"format=yuv420p,eq=gamma=1.05,setsar=1,fps={fps}")
    else:
        vf.append(f"scale={width}:{height}:flags=lanczos,setsar=1,fps={fps}")
    if seg.get("fx") == "hit":
        # A short shake on the impact frame and a white flash that settles.
        vf.append("scale=iw*1.06:ih*1.06,"
                  f"crop={width}:{height}:'(in_w-out_w)/2+if(lte(t,0.45),sin(t*55)*18,0)':"
                  "'(in_h-out_h)/2+if(lte(t,0.45),cos(t*47)*18,0)'")
        vf.append("fade=t=in:st=0:d=0.22:color=white")
    if seg.get("text"):
        # A big centred word, punched in with a short fade.
        word, show = seg["text"]
        vf.append(f"drawtext=fontfile={BIG_FONT}:text='{word}':fontcolor={accent}:"
                  f"fontsize={int(min(width, height) * float(seg.get('text_size', 0.16)))}:x=(w-tw)/2:y=(h-th)/2:"
                  f"borderw=6:bordercolor=black@0.85:enable='lt(t,{show})':"
                  f"alpha='if(lt(t,0.12),t/0.12,if(gt(t,{show}-0.25),({show}-t)/0.25,1))'")
    if hold > 0:
        vf.append(f"tpad=stop_mode=clone:stop_duration={hold:.3f}")

    af = []
    if speed != 1.0:
        af.append(_atempo(speed))
    if seg["audio"] == "mute":
        af.append("volume=0")
    elif seg["audio"] == "bed":
        af.append("volume=-9dB")
    af.append("aformat=sample_rates=48000:channel_layouts=stereo")
    if hold > 0:
        af.append(f"apad=pad_dur={hold:.3f}")

    subprocess.run([
        "ffmpeg", "-y", "-v", "error",
        "-ss", f"{seg['src_in']:.3f}", "-t", f"{read:.3f}", "-i", seg["src"],
        "-vf", ",".join(vf), "-af", ",".join(af),
        "-c:v", "libx264", "-preset", "fast", "-crf", "17", "-pix_fmt", "yuv420p", "-r", str(fps),
        "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
        "-c:a", "aac", "-b:a", "192k", "-t", f"{seg['length']:.3f}", str(dest),
    ], check=True, cwd=PROJECT_ROOT)


def render_segments(segments: List[Dict], work: Path, width: int, height: int, fps: int = 30,
                    accent: str = "#F3D340", log=print) -> List[Path]:
    """Renders every segment, skipping ones already rendered with the same settings."""
    work.mkdir(parents=True, exist_ok=True)
    pieces = []
    for i, seg in enumerate(segments):
        key = hashlib.md5(json.dumps({**{k: v for k, v in seg.items() if k not in ("t0", "t1")},
                                      "hdr": bool(seg.get("src")) and is_hdr(seg["src"])},
                                     sort_keys=True, default=str).encode()).hexdigest()[:8]
        dest = work / f"seg_{i:02d}_{seg['name']}_{key}.mp4"
        if not dest.exists():
            render_segment(seg, dest, width, height, fps, accent)
            log(f"    rendered {seg['name']} ({seg['length']:.1f}s)")
        pieces.append(dest)
    return pieces


def concat(pieces: List[Path], dest: Path) -> None:
    listing = dest.with_suffix(".txt")
    listing.write_text("".join(f"file '{p.resolve().as_posix()}'\n" for p in pieces), encoding="utf-8")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(listing),
                    "-c", "copy", str(dest)], check=True)


# --- Narration mix ------------------------------------------------------------------


def measure_lufs(path: Path) -> float:
    out = subprocess.run(["ffmpeg", "-v", "info", "-i", str(path), "-af", "loudnorm=print_format=json",
                          "-f", "null", "-"], capture_output=True, text=True).stderr
    match = re.search(r"\{.*\}", out, re.S)
    return float(json.loads(match.group(0))["input_i"]) if match else -23.0


def mix_narration(track: Path, lines: List[Dict], dest: Path, total: float, source_lufs: float = -18.0) -> None:
    """Source audio levelled to `source_lufs`, ducked under the narration lines."""
    gain = source_lufs - measure_lufs(track)
    inputs = ["-i", str(track)]
    parts = [f"[0:a]volume={gain:.2f}dB[src]"]
    labels = []
    for i, line in enumerate(lines, start=1):
        inputs += ["-i", line["audio"]]
        ms = int(round(line["t0"] * 1000))
        parts.append(f"[{i}:a]adelay={ms}|{ms}[n{i}]")
        labels.append(f"[n{i}]")
    if labels:
        parts.append(f"{''.join(labels)}amix=inputs={len(labels)}:duration=longest:normalize=0,"
                     f"apad=whole_dur={total:.3f},asplit=2[nar_key][nar_mix]")
        parts.append("[src][nar_key]sidechaincompress=threshold=0.02:ratio=7:attack=25:release=600:makeup=1[ducked]")
        # ~2 dB of headroom for the finisher, which adds music and effects on
        # top behind a sample-peak limiter. level=false: alimiter otherwise
        # auto-gains the whole mix up to its ceiling.
        parts.append("[ducked][nar_mix]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.8:level=false[out]")
    else:
        parts.append("[src]alimiter=limit=0.8:level=false[out]")
    subprocess.run([
        "ffmpeg", "-y", "-v", "error", *inputs,
        "-filter_complex", ";".join(parts),
        "-map", "0:v", "-map", "[out]", "-c:v", "copy", "-c:a", "aac", "-b:a", "256k",
        "-t", f"{total:.3f}", "-movflags", "+faststart", str(dest),
    ], check=True)


# --- Captions and finishing -------------------------------------------------------------


def words_from_lines(dialogue: List) -> List[Dict]:
    """(start, end, text) lines as timed words: each span shared out by word length."""
    out = []
    for start, end, text in dialogue:
        tokens = text.split()
        weights = [max(2, len(re.sub(r"[^A-Za-z0-9']", "", t))) for t in tokens]
        span, total = end - start, sum(weights)
        t = start
        for token, weight in zip(tokens, weights):
            length = span * weight / total
            out.append({"word": token, "start": round(t, 3), "end": round(t + length, 3)})
            t += length
    return out


def timeline_words(segments: List[Dict], source_words: List[Dict], lines: List[Dict]) -> List[Dict]:
    """Narration words plus source dialogue that plays at full speed, in output time."""
    out = []
    for seg in segments:
        if seg.get("black") or seg["audio"] != "source" or seg["speed"] != 1.0:
            continue
        for w in source_words:
            if seg["src_in"] <= w["start"] < seg["src_out"]:
                out.append({"word": w["word"], "start": round(seg["t0"] + w["start"] - seg["src_in"], 3),
                            "end": round(min(seg["t1"], seg["t0"] + w["end"] - seg["src_in"]), 3)})
    for line in lines:
        for w in line["words"]:
            out.append({"word": w["word"], "start": round(line["t0"] + w["start"], 3),
                        "end": round(line["t0"] + w["end"], 3)})
    out.sort(key=lambda w: w["start"])
    # The caption engine wants a strictly ordered, non-overlapping list.
    for a, b in zip(out, out[1:]):
        if b["start"] < a["end"]:
            a["end"] = round(max(a["start"] + 0.05, b["start"]), 3)
    return out


def clamp_overlays(overlays: List[Dict], total: float) -> List[Dict]:
    for o in overlays:
        o["start"], o["end"] = round(o["start"], 2), min(round(o["end"], 2), round(total, 3))
    return overlays


def compile_captions(config_path: Path, ass_path: Path, srt_path: Path) -> None:
    subprocess.run([sys.executable, str(PROJECT_ROOT / "graphics_tool.py"), "compile",
                    "--config", str(config_path), "--output", str(ass_path), "--srt", str(srt_path),
                    "--overwrite"], check=True, stdout=subprocess.DEVNULL)


def finish(config_path: Path, clean: Path, final: Path, report: Optional[Path] = None) -> Path:
    """Graphics, captions, and the required Epidemic music/SFX, via graphics_tool."""
    result = subprocess.run([
        sys.executable, str(PROJECT_ROOT / "graphics_tool.py"), "render",
        "--config", str(config_path), "--input", str(clean), "--output", str(final),
        "--encoder", "auto", "--fonts-dir", str(FONTS_DIR), "--overwrite",
    ], check=True, capture_output=True, text=True).stdout
    match = re.search(r"\{.*\}", result, re.S)
    if report and match:
        report.write_text(match.group(0), encoding="utf-8")
    return final
