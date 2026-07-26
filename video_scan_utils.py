"""Shared helpers for the frame-scanning scripts.

Centralises the three things every scanner needs: where the media lives,
how frames get extracted, and the skin-tone heuristic - which previously
existed in three copies with three different thresholds.
"""

import glob
import os
import re
import shutil
import subprocess
from pathlib import Path

import cv2
import numpy as np
from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent
MEDIA_ROOT = os.getenv("MEDIA_ROOT", str(PROJECT_ROOT / "media"))
MILITARY_VIDEOS_DIR = os.getenv("MILITARY_VIDEOS_DIR", os.path.join(MEDIA_ROOT, "US Military"))
OUTPUT_DIR = os.getenv("OUTPUT_DIR", str(PROJECT_ROOT / "output"))

# Default subject used by the DOD analysis scripts; override with argv[1].
DEFAULT_VIDEO = os.path.join(MILITARY_VIDEOS_DIR, "DOD_107190749.mp4")

# Fraction of frame pixels matching skin tone above which a frame is treated
# as containing a person. Tune in one place, not three.
SKIN_RATIO_THRESHOLD = 0.03


def open_video(video_path):
    """Open a video, returning (capture, fps, total_frames, duration).

    Raises a clear error rather than dividing by a zero fps later on.
    """
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video not found: {video_path}")

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if not fps or fps <= 0:
        cap.release()
        raise RuntimeError(f"Video reports invalid fps ({fps}): {video_path}")

    return cap, fps, total_frames, total_frames / fps


def extract_frames(video_path, output_dir, fps_filter, prefix="frame"):
    """Extract frames with ffmpeg and return them sorted by frame index.

    Clears output_dir first so a short run cannot inherit frames from a
    previous longer one. Uses 5-digit numbering because %02d/%03d break
    ordering once the count rolls past the padding width.
    """
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video not found: {video_path}")

    if os.path.isdir(output_dir):
        shutil.rmtree(output_dir)
    os.makedirs(output_dir, exist_ok=True)

    pattern = os.path.join(output_dir, f"{prefix}_%05d.jpg")
    cmd = ["ffmpeg", "-y", "-i", video_path, "-vf", f"fps={fps_filter}", pattern]
    try:
        subprocess.run(cmd, check=True, capture_output=True)
    except FileNotFoundError:
        raise RuntimeError("ffmpeg not found on PATH - install it or add it to PATH.")
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.decode("utf-8", errors="replace")[-500:] if exc.stderr else ""
        raise RuntimeError(f"ffmpeg failed extracting frames:\n{stderr}")

    files = glob.glob(os.path.join(output_dir, f"{prefix}_*.jpg"))
    return sorted(files, key=frame_index)


def frame_index(path):
    """Parse the numeric index out of a frame filename."""
    match = re.search(r"_(\d+)\.jpg$", os.path.basename(path))
    if not match:
        raise ValueError(f"Unexpected frame filename: {path}")
    return int(match.group(1))


def frame_timestamp(path, interval_seconds):
    """Convert a frame filename to its timestamp in seconds.

    ffmpeg numbers output frames from 1, so the first frame is t=0 - hence
    the -1. Without it every timestamp is shifted by one interval.
    """
    return round((frame_index(path) - 1) * interval_seconds, 2)


def skin_ratio(img):
    """Fraction of pixels matching a skin-tone heuristic (BGR input)."""
    b = img[:, :, 0].astype(np.int16)
    g = img[:, :, 1].astype(np.int16)
    r = img[:, :, 2].astype(np.int16)

    max_c = np.maximum(r, np.maximum(g, b))
    min_c = np.minimum(r, np.minimum(g, b))

    mask = (
        (r > 95) & (g > 40) & (b > 20)
        & ((max_c - min_c) > 15)
        & (np.abs(r - g) > 15)
        & (r > g) & (r > b)
    )
    return float(np.sum(mask)) / (img.shape[0] * img.shape[1])


def to_segments(timestamps, sample_interval, min_duration=2.0):
    """Collapse sampled timestamps into continuous (start, end) segments.

    A gap larger than 1.5x the sampling interval means at least one sample
    was excluded, so the segment is cut there. Using a fixed threshold (the
    previous 1.0s) let excluded samples stay inside a segment whenever the
    sampling interval was smaller than the threshold.
    """
    if not timestamps:
        return []

    gap_threshold = sample_interval * 1.5
    segments = []
    start = prev = timestamps[0]

    for ts in timestamps[1:]:
        if ts - prev > gap_threshold:
            if prev - start >= min_duration:
                segments.append((round(start, 2), round(prev, 2)))
            start = ts
        prev = ts

    if prev - start >= min_duration:
        segments.append((round(start, 2), round(prev, 2)))

    return segments
