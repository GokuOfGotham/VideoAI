"""
Visual HUD Validator for VideoAI (Smart Pass Detection Policy).

Performs instantaneous coarse video trimming via FFmpeg stream copying (-c copy),
followed by targeted OpenCV template matching (cv2.matchTemplate) to detect HUD
combat cues (hit markers, kill badges, reticle flares) across candidate clips.
"""

import glob
import os
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np


def get_video_duration(video_path: str, ffprobe_binary: str = "ffprobe") -> float:
    """Retrieves video duration in seconds via ffprobe."""
    cmd = [
        ffprobe_binary,
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        video_path
    ]
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        return float(res.stdout.strip())
    except Exception:
        # Fallback to cv2
        cap = cv2.VideoCapture(video_path)
        if cap.isOpened():
            fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
            frames = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
            cap.release()
            if fps > 0:
                return frames / fps
        return 0.0


def trim_candidate_clip_stream_copy(
    video_path: str,
    peak_timestamp_sec: float,
    output_clip_path: str,
    clip_duration: float = 30.0,
    padding_before: float = 15.0,
    video_duration: Optional[float] = None,
    ffmpeg_binary: str = "ffmpeg"
) -> Dict[str, Any]:
    """
    Carves out a coarse 30-second candidate clip around an audio peak.
    Uses FFmpeg stream copying (-c copy) for instantaneous zero-re-encode trimming.
    """
    os.makedirs(os.path.dirname(os.path.abspath(output_clip_path)), exist_ok=True)

    start_sec = max(0.0, peak_timestamp_sec - padding_before)
    if video_duration and video_duration > 0:
        if start_sec + clip_duration > video_duration:
            start_sec = max(0.0, video_duration - clip_duration)

    # Placing -ss before -i triggers fast keyframe seeking with -c copy
    cmd = [
        ffmpeg_binary,
        "-y",
        "-ss", f"{start_sec:.2f}",
        "-i", video_path,
        "-t", f"{clip_duration:.2f}",
        "-c", "copy",
        "-avoid_negative_ts", "1",
        output_clip_path
    ]

    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if res.returncode != 0:
        err = res.stderr[-400:] if res.stderr else "Unknown error"
        raise RuntimeError(f"FFmpeg coarse trimming failed:\n{err}")

    if not os.path.isfile(output_clip_path) or os.path.getsize(output_clip_path) == 0:
        raise RuntimeError(f"Trimmed clip is missing or 0 bytes: {output_clip_path}")

    return {
        "clip_path": output_clip_path,
        "peak_sec": peak_timestamp_sec,
        "start_sec": start_sec,
        "duration": clip_duration
    }


class HUDTemplateMatcher:
    """
    Manages gaming HUD reference templates (hit markers, kill badges, combat UI)
    and performs multi-scale template matching via cv2.matchTemplate.
    """

    def __init__(self, templates_dir: Optional[str] = None):
        if templates_dir is None:
            # Default to assets/hud_templates in VideoAI project
            base_dir = Path(__file__).resolve().parent
            templates_dir = str(base_dir / "assets" / "hud_templates")

        self.templates_dir = templates_dir
        os.makedirs(self.templates_dir, exist_ok=True)
        self.templates: Dict[str, np.ndarray] = {}
        self._ensure_default_templates()
        self.load_templates()

    def _ensure_default_templates(self):
        """Generates standard high-contrast synthetic gaming templates if folder is empty."""
        existing = glob.glob(os.path.join(self.templates_dir, "*.png"))
        if existing:
            return

        print(f"[*] Generating standard HUD reference templates in {self.templates_dir}...")

        # 1. Standard diagonal hitmarker cross ("X")
        hm = np.zeros((32, 32), dtype=np.uint8)
        # Draw 4 angled tic marks radiating from center
        cv2.line(hm, (7, 7), (12, 12), 255, 2)
        cv2.line(hm, (24, 7), (19, 12), 255, 2)
        cv2.line(hm, (7, 24), (12, 19), 255, 2)
        cv2.line(hm, (24, 24), (19, 19), 255, 2)
        cv2.imwrite(os.path.join(self.templates_dir, "hitmarker_standard.png"), hm)

        # 2. Critical / Kill red hitmarker
        hm_crit = np.zeros((36, 36, 3), dtype=np.uint8)
        cv2.line(hm_crit, (6, 6), (13, 13), (0, 0, 255), 2)
        cv2.line(hm_crit, (29, 6), (22, 13), (0, 0, 255), 2)
        cv2.line(hm_crit, (6, 29), (13, 22), (0, 0, 255), 2)
        cv2.line(hm_crit, (29, 29), (22, 22), (0, 0, 255), 2)
        cv2.imwrite(os.path.join(self.templates_dir, "hitmarker_crit.png"), hm_crit)

        # 3. Universal Kill Skull Badge silhouette
        skull = np.zeros((40, 40), dtype=np.uint8)
        cv2.circle(skull, (20, 16), 12, 255, -1)     # Cranium
        cv2.rectangle(skull, (14, 20), (26, 32), 255, -1) # Jaw
        cv2.circle(skull, (16, 17), 3, 0, -1)       # Left eye
        cv2.circle(skull, (24, 17), 3, 0, -1)       # Right eye
        cv2.line(skull, (17, 29), (17, 32), 0, 1)   # Teeth cuts
        cv2.line(skull, (20, 28), (20, 32), 0, 1)
        cv2.line(skull, (23, 29), (23, 32), 0, 1)
        cv2.imwrite(os.path.join(self.templates_dir, "kill_badge_skull.png"), skull)

    def load_templates(self):
        """Loads all grayscale template images from templates directory."""
        self.templates.clear()
        img_paths = glob.glob(os.path.join(self.templates_dir, "*.*"))
        for p in img_paths:
            if p.lower().endswith((".png", ".jpg", ".jpeg")):
                tpl = cv2.imread(p, cv2.IMREAD_GRAYSCALE)
                if tpl is not None:
                    self.templates[Path(p).stem] = tpl
        print(f"[+] Loaded {len(self.templates)} HUD reference templates: {list(self.templates.keys())}")

    def match_frame(
        self,
        frame_gray: np.ndarray,
        threshold: float = 0.72,
        scales: Tuple[float, ...] = (0.8, 1.0, 1.3, 1.8, 2.4),
        center_roi_ratio: float = 0.45
    ) -> Dict[str, Any]:
        """
        Scans a frame using cv2.matchTemplate against loaded HUD templates.
        Focuses on center HUD screen area (where hitmarkers and reticles appear)
        for extreme speed and rejection of background clutter.
        """
        h, w = frame_gray.shape[:2]
        # Crop center region of interest for reticle / hitmarkers
        cy, cx = h // 2, w // 2
        ry, rx = int(h * center_roi_ratio / 2.0), int(w * center_roi_ratio / 2.0)
        roi = frame_gray[max(0, cy - ry):min(h, cy + ry), max(0, cx - rx):min(w, cx + rx)]

        best_score = 0.0
        best_name = None
        best_loc = (0, 0)

        for name, tpl in self.templates.items():
            th, tw = tpl.shape[:2]
            for s in scales:
                sw, sh = int(tw * s), int(th * s)
                if sw >= roi.shape[1] or sh >= roi.shape[0] or sw < 8 or sh < 8:
                    continue

                scaled_tpl = cv2.resize(tpl, (sw, sh), interpolation=cv2.INTER_AREA if s < 1.0 else cv2.INTER_LINEAR)
                # Normalized correlation coefficient
                res = cv2.matchTemplate(roi, scaled_tpl, cv2.TM_CCOEFF_NORMED)
                _, max_val, _, max_loc = cv2.minMaxLoc(res)

                if max_val > best_score:
                    best_score = float(max_val)
                    best_name = name
                    best_loc = max_loc

        return {
            "matched": best_score >= threshold,
            "score": round(best_score, 3),
            "template": best_name if best_score >= threshold else None,
            "location": best_loc
        }


def validate_candidate_clip(
    clip_path: str,
    matcher: Optional[HUDTemplateMatcher] = None,
    sample_fps: float = 2.0,
    match_threshold: float = 0.70,
    min_confirmations: int = 2
) -> Dict[str, Any]:
    """
    Smart Pass Visual Validation:
    Opens only the 30-second candidate clip and samples ~60 frames.
    Performs HUD template matching and frame-difference motion analysis.
    Returns structured validation metrics.
    """
    if not os.path.isfile(clip_path):
        return {"is_valid": False, "reason": "Clip file does not exist", "score": 0.0}

    if matcher is None:
        matcher = HUDTemplateMatcher()

    cap = cv2.VideoCapture(clip_path)
    if not cap.isOpened():
        return {"is_valid": False, "reason": "Could not open clip with OpenCV", "score": 0.0}

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 0
    step = max(1, int(round(fps / sample_fps)))

    frame_idx = 0
    prev_gray = None
    motion_scores = []
    hud_matches = []

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            frame_idx += 1
            if frame_idx % step != 0:
                continue

            sec = round(frame_idx / fps, 2)
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

            # Motion velocity check (detects static menus vs active gameplay)
            if prev_gray is not None:
                motion = float(np.mean(cv2.absdiff(gray, prev_gray)))
                motion_scores.append(motion)
            prev_gray = gray

            # HUD Template Match
            match_res = matcher.match_frame(gray, threshold=match_threshold)
            if match_res["matched"]:
                hud_matches.append({
                    "time_sec": sec,
                    "template": match_res["template"],
                    "score": match_res["score"]
                })
    finally:
        cap.release()

    avg_motion = float(np.mean(motion_scores)) if motion_scores else 0.0
    is_static = avg_motion < 1.8  # Inactive menu screen / pause screen
    hit_count = len(hud_matches)

    # Validated if we have confirmed combat HUD hits AND significant on-screen motion
    is_valid = (hit_count >= min_confirmations) and not is_static
    max_score = max([m["score"] for m in hud_matches], default=0.0)

    return {
        "clip_path": clip_path,
        "is_valid": is_valid,
        "hud_hits": hit_count,
        "max_score": max_score,
        "avg_motion": round(avg_motion, 2),
        "is_static": is_static,
        "matched_events": hud_matches[:10],
        "reason": "VERIFIED COMBAT HUD ACTION" if is_valid else (
            "Static screen" if is_static else "Insufficient HUD action cues"
        )
    }
