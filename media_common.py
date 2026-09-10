"""Shared media helpers for the VideoAI sourcing tiers.

FFmpeg probing, shot detection and clip normalisation used by every media
sourcer, so the b-roll, NASA and SpaceX tiers all emit clips the renderer can
concatenate without re-encoding surprises.
"""

import os
import re
import subprocess
from pathlib import Path
from typing import List, Optional, Tuple

import requests

DEFAULT_RESOLUTION = (1080, 1920)
MIN_USABLE_BYTES = 10_000


def env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, "") or default)
    except ValueError:
        return default


def env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, "") or default)
    except ValueError:
        return default


def target_resolution(env_name: str = "YOUTUBE_BROLL_RESOLUTION") -> Tuple[int, int]:
    """Parses a WxH override, falling back to vertical 1080x1920."""
    raw = os.getenv(env_name, "").lower().strip()
    match = re.fullmatch(r"(\d+)\s*x\s*(\d+)", raw)
    if not match:
        return DEFAULT_RESOLUTION
    return int(match.group(1)), int(match.group(2))


def media_duration(path: Path) -> float:
    """Returns a media file's duration in seconds, or 0.0 if unreadable."""
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return float(res.stdout.strip())
    except (subprocess.SubprocessError, OSError, ValueError):
        return 0.0


def detect_scene_cuts(path: Path, threshold: Optional[float] = None) -> List[float]:
    """Returns timestamps of hard cuts in a clip, via FFmpeg scene scores."""
    if threshold is None:
        threshold = env_float("YOUTUBE_BROLL_SCENE_THRESHOLD", 0.30)
    select_expr = f"select='gt(scene,{threshold})',metadata=print:file=-"
    cmd = [
        "ffmpeg", "-hide_banner", "-nostats",
        "-i", str(path),
        "-an", "-sn",
        "-filter:v", select_expr,
        "-f", "null", "-",
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    except (subprocess.SubprocessError, OSError):
        return []

    stream = f"{res.stdout}\n{res.stderr}"
    return sorted({float(t) for t in re.findall(r"pts_time:([0-9.]+)", stream)})


def pick_longest_shot(cuts: List[float], duration: float, clip_length: float) -> float:
    """Returns the offset of the longest uninterrupted shot in a window.

    Continuous footage cuts better under narration than a segment that happens
    to straddle an edit, so the longest gap between detected cuts wins.
    """
    if duration <= clip_length:
        return 0.0

    boundaries = [0.0] + [c for c in cuts if 0.0 < c < duration] + [duration]
    best_start, best_length = 0.0, 0.0
    for start, end in zip(boundaries, boundaries[1:]):
        if end - start > best_length:
            best_start, best_length = start, end - start

    if best_length < clip_length:
        return max(0.0, (duration - clip_length) / 2)

    # Centre the cut inside the shot, away from the edits at either edge.
    return min(best_start + (best_length - clip_length) / 2, duration - clip_length)


def _vertical_filter(width: int, height: int, fps: int) -> str:
    return (
        f"scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height},setsar=1,fps={fps}"
    )


def normalise_clip(source: Path, dest: Path, offset: float, length: float) -> bool:
    """Cuts `length` seconds from `offset` and renders a muted vertical clip."""
    width, height = target_resolution()
    fps = env_int("YOUTUBE_BROLL_FPS", 30)
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-nostats", "-loglevel", "error",
        "-ss", f"{offset:.3f}",
        "-t", f"{length:.3f}",
        "-i", str(source),
        "-an",
        "-vf", _vertical_filter(width, height, fps),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-pix_fmt", "yuv420p",
        str(dest),
    ]
    return _run_ffmpeg(cmd, dest)


def still_to_clip(source: Path, dest: Path, length: float) -> bool:
    """Turns a still image into a slow-push vertical clip.

    NASA and SpaceX return a lot of stills, and a static frame under narration
    reads as a broken video, so the image gets a gentle Ken Burns move. The
    input is upscaled first because zoompan steps in whole source pixels and
    jitters visibly at native size.
    """
    width, height = target_resolution()
    fps = env_int("YOUTUBE_BROLL_FPS", 30)
    frames = max(1, int(round(length * fps)))
    zoom_rate = env_float("SPACE_MEDIA_ZOOM_RATE", 0.0006)

    vf = (
        f"scale=4000:-2,"
        f"zoompan=z='min(zoom+{zoom_rate},1.25)':d={frames}"
        f":x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
        f":s={width}x{height}:fps={fps},"
        f"setsar=1"
    )
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-nostats", "-loglevel", "error",
        "-loop", "1",
        "-i", str(source),
        "-t", f"{length:.3f}",
        "-an",
        "-vf", vf,
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-pix_fmt", "yuv420p",
        str(dest),
    ]
    if _run_ffmpeg(cmd, dest):
        return True

    # zoompan can fail on unusual colour spaces; a static crop still beats nothing.
    fallback = [
        "ffmpeg", "-y", "-hide_banner", "-nostats", "-loglevel", "error",
        "-loop", "1", "-i", str(source), "-t", f"{length:.3f}", "-an",
        "-vf", _vertical_filter(width, height, fps),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-pix_fmt", "yuv420p", str(dest),
    ]
    return _run_ffmpeg(fallback, dest)


def _run_ffmpeg(cmd: List[str], dest: Path) -> bool:
    try:
        subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=300)
    except subprocess.CalledProcessError as exc:
        print(f"[MediaCommon] FFmpeg failed: {(exc.stderr or '')[-300:]}")
        return False
    except (subprocess.SubprocessError, OSError) as exc:
        print(f"[MediaCommon] FFmpeg failed ({exc}).")
        return False
    return dest.exists() and dest.stat().st_size > MIN_USABLE_BYTES


def download_file(url: str, dest: Path, timeout: int = 60) -> bool:
    """Streams a URL to disk, returning False rather than raising."""
    try:
        with requests.get(url, stream=True, timeout=timeout,
                          headers={"User-Agent": "VideoAI/1.0"}) as resp:
            resp.raise_for_status()
            dest.parent.mkdir(parents=True, exist_ok=True)
            with open(dest, "wb") as f:
                for chunk in resp.iter_content(chunk_size=64 * 1024):
                    if chunk:
                        f.write(chunk)
    except Exception as exc:
        print(f"[MediaCommon] Download failed ({exc}).")
        dest.unlink(missing_ok=True)
        return False

    if dest.exists() and dest.stat().st_size > MIN_USABLE_BYTES:
        return True
    dest.unlink(missing_ok=True)
    return False
