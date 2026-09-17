"""Shared FFmpeg/ffprobe helpers for the editing room tools."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Sequence

import numpy as np


class EditRoomError(RuntimeError):
    """A tool could not complete; the message says what to fix."""


def _tool(name: str, override: str | None = None) -> str:
    executable = override or os.environ.get(name.upper()) or name
    if shutil.which(executable) is None and not Path(executable).exists():
        raise EditRoomError(f"{name} was not found on PATH; install FFmpeg or pass --{name}.")
    return executable


def run_ffmpeg(args: Sequence[str], *, ffmpeg: str | None = None, timeout: float | None = None) -> str:
    """Runs ffmpeg with `args` (no leading binary), returning stderr for parsers."""
    command = [_tool("ffmpeg", ffmpeg), "-hide_banner", "-nostdin", "-y", *args]
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8",
                            errors="replace", timeout=timeout)
    if result.returncode != 0:
        tail = "\n".join(result.stderr.strip().splitlines()[-8:])
        raise EditRoomError(f"ffmpeg failed ({result.returncode}):\n{tail}")
    return result.stderr


def ffprobe_json(path: str | Path, *, ffprobe: str | None = None) -> dict[str, Any]:
    path = Path(path)
    if not path.exists():
        raise EditRoomError(f"Media not found: {path}")
    result = subprocess.run([_tool("ffprobe", ffprobe), "-v", "error", "-print_format", "json",
                             "-show_format", "-show_streams", str(path)],
                            capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode != 0:
        raise EditRoomError(f"ffprobe could not read {path.name}: {result.stderr.strip()[-300:]}")
    return json.loads(result.stdout or "{}")


def media_duration(path: str | Path, *, ffprobe: str | None = None) -> float:
    info = ffprobe_json(path, ffprobe=ffprobe)
    value = info.get("format", {}).get("duration")
    if value is None:
        for stream in info.get("streams", []):
            if stream.get("duration"):
                value = stream["duration"]
                break
    if value is None:
        raise EditRoomError(f"Could not determine the duration of {Path(path).name}.")
    return float(value)


def video_stream(info: dict[str, Any]) -> dict[str, Any] | None:
    return next((s for s in info.get("streams", []) if s.get("codec_type") == "video"), None)


def audio_streams(info: dict[str, Any]) -> list[dict[str, Any]]:
    return [s for s in info.get("streams", []) if s.get("codec_type") == "audio"]


def frame_rate(info: dict[str, Any], default: float = 30.0) -> float:
    stream = video_stream(info)
    if not stream:
        return default
    for key in ("avg_frame_rate", "r_frame_rate"):
        value = stream.get(key) or ""
        if "/" in value:
            num, den = value.split("/", 1)
            if float(den) > 0 and float(num) > 0:
                return float(num) / float(den)
    return default


def decode_mono(path: str | Path, rate: int = 8000, *, start: float | None = None,
                duration: float | None = None, ffmpeg: str | None = None) -> np.ndarray:
    """Decodes the first audio stream to float32 mono samples at `rate` Hz."""
    args: list[str] = []
    if start is not None:
        args += ["-ss", f"{start:.3f}"]
    args += ["-i", str(path)]
    if duration is not None:
        args += ["-t", f"{duration:.3f}"]
    args += ["-map", "0:a:0", "-ac", "1", "-ar", str(rate), "-f", "f32le", "-"]
    command = [_tool("ffmpeg", ffmpeg), "-hide_banner", "-nostdin", "-v", "error", *args]
    result = subprocess.run(command, capture_output=True)
    if result.returncode != 0:
        raise EditRoomError(f"Could not decode audio from {Path(path).name}: "
                            f"{result.stderr.decode('utf-8', 'replace').strip()[-300:]}")
    return np.frombuffer(result.stdout, dtype=np.float32)


def timecode(seconds: float, fps: float = 30.0) -> str:
    """HH:MM:SS:FF timecode for reports and XML markers."""
    seconds = max(0.0, float(seconds))
    frames = int(round((seconds - int(seconds)) * fps))
    whole = int(seconds)
    if frames >= int(round(fps)):
        frames = 0
        whole += 1
    return f"{whole // 3600:02d}:{(whole % 3600) // 60:02d}:{whole % 60:02d}:{frames:02d}"


def write_json(path: str | Path, data: Any) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return path
