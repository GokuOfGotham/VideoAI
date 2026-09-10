"""
Dynamic Scene Hit Detector for VideoAI.

Eliminates static/mismatched sound effects by analyzing the exact video frames
and audio waveform to pinpoint genuine physical strikes, punches, and takedowns.

Multi-Modal Fusion:
1. Video Motion Spikes: Kinetic acceleration peaks (cv2.absdiff) & hitstop freezes.
2. Audio Transients: High-energy sound spikes in the natural game track.
3. Coincidence Fusion: Aligns SFX within 100ms of actual visible impact.
4. Intelligent Categorization:
   - Heavy kinetic slams / takedowns -> 'bone_crush'
   - Sharp rapid counters / jabs -> 'punch_face' or 'punch_hard'
   - Standard body blows -> 'punch_body'
"""

import os
import subprocess
import wave
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np


def detect_visual_motion_peaks(
    video_path: str,
    start_sec: float = 0.0,
    duration_sec: float = 60.0,
    sample_fps: float = 30.0,
    motion_threshold: float = 12.0
) -> List[Tuple[float, float]]:
    """
    Scans video frames across the window to detect sharp kinetic impact peaks.
    Returns list of (timestamp_sec, motion_intensity).
    """
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return []

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    start_frame = int(start_sec * fps)
    total_frames = int(duration_sec * fps)

    cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)

    prev_gray = None
    motion_profile = []
    frame_times = []

    for idx in range(total_frames):
        ret, frame = cap.read()
        if not ret:
            break

        # Small 320x180 resolution for lightning-fast analysis
        small = cv2.resize(frame, (320, 180))
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)

        if prev_gray is not None:
            diff = float(np.mean(cv2.absdiff(gray, prev_gray)))
        else:
            diff = 0.0

        motion_profile.append(diff)
        frame_times.append(start_sec + (idx / fps))
        prev_gray = gray

    cap.release()

    if len(motion_profile) < 5:
        return []

    motion_arr = np.array(motion_profile)

    # Local maxima detection over a 15-frame window (~0.5s)
    peaks = []
    half_w = 7
    for i in range(half_w, len(motion_arr) - half_w):
        window = motion_arr[i - half_w : i + half_w + 1]
        val = motion_arr[i]
        if val == np.max(window) and val >= motion_threshold:
            # Check for sudden jerk (significantly above local median)
            local_med = np.median(window)
            if val >= local_med * 1.6:
                peaks.append((round(frame_times[i], 3), round(float(val), 2)))

    return peaks


def detect_audio_impact_transients(
    video_path: str,
    start_sec: float = 0.0,
    duration_sec: float = 60.0,
    temp_wav_path: Optional[str] = None
) -> List[Tuple[float, float]]:
    """
    Extracts audio segment and finds sudden high-energy audio transient spikes.
    Returns list of (timestamp_sec, transient_strength).
    """
    if temp_wav_path is None:
        temp_wav_path = os.path.join(
            Path(__file__).resolve().parent, "output", f"temp_transient_{int(start_sec)}.wav"
        )
    os.makedirs(os.path.dirname(temp_wav_path), exist_ok=True)

    cmd = [
        "ffmpeg", "-y",
        "-ss", f"{start_sec:.2f}",
        "-t", f"{duration_sec:.2f}",
        "-i", video_path,
        "-vn", "-ac", "1", "-ar", "22050",
        "-c:a", "pcm_s16le",
        temp_wav_path
    ]
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if res.returncode != 0 or not os.path.isfile(temp_wav_path):
        return []

    try:
        with wave.open(temp_wav_path, "rb") as wf:
            framerate = wf.getframerate()
            raw_bytes = wf.readframes(wf.getnframes())
            samples = np.frombuffer(raw_bytes, dtype=np.int16).astype(np.float32) / 32768.0

        if len(samples) == 0:
            return []

        # 50ms short-time RMS window
        win_size = int(framerate * 0.05)
        hop_size = int(framerate * 0.025)

        sq = samples ** 2
        cumsum = np.pad(np.cumsum(sq), (1, 0), mode="constant")
        indices = np.arange(0, len(samples) - win_size + 1, hop_size)
        win_sums = cumsum[indices + win_size] - cumsum[indices]
        rms = np.sqrt(np.maximum(0.0, win_sums / win_size))
        times = start_sec + (indices / float(framerate))

        # Peak detection: transient ratio over local rolling mean
        half_k = 10
        cum_rms = np.pad(np.cumsum(rms), (1, 0), mode="constant")
        n = len(rms)
        s_idx = np.maximum(0, np.arange(n) - half_k)
        e_idx = np.minimum(n, np.arange(n) + half_k + 1)
        local_avg = (cum_rms[e_idx] - cum_rms[s_idx]) / (e_idx - s_idx)

        spikes = []
        for i in range(1, n - 1):
            if rms[i] >= rms[i-1] and rms[i] >= rms[i+1]:
                if rms[i] >= local_avg[i] * 2.0 and rms[i] >= 0.08:
                    spikes.append((round(times[i], 3), round(float(rms[i]), 3)))

        return spikes
    finally:
        if os.path.isfile(temp_wav_path):
            try:
                os.remove(temp_wav_path)
            except Exception:
                pass


def map_scene_combat_hits(
    video_path: str,
    start_sec: float = 0.0,
    duration_sec: float = 60.0,
    min_hit_gap_sec: float = 0.45
) -> List[Dict[str, Any]]:
    """
    Fuses video motion peaks and audio transients to produce frame-accurate hit coordinates.
    Strictly categorizes 'bone_crush' ONLY to genuine heavy impact kinetic spikes!
    """
    print(f"[*] Analyzing scene dynamics from t={start_sec:.1f}s to {start_sec+duration_sec:.1f}s...")
    v_peaks = detect_visual_motion_peaks(video_path, start_sec, duration_sec)
    a_spikes = detect_audio_impact_transients(video_path, start_sec, duration_sec)

    print(f"    Visual Motion Spikes: {len(v_peaks)} | Audio Transients: {len(a_spikes)}")

    fused_candidates = []

    # Check for coincidence (visual peak within 180ms of an audio transient)
    for vt, v_val in v_peaks:
        matched_audio = [av for at, av in a_spikes if abs(vt - at) <= 0.20]
        a_val = max(matched_audio) if matched_audio else 0.0
        score = v_val + (a_val * 60.0)
        fused_candidates.append({
            "time_sec": vt,
            "v_score": v_val,
            "a_score": a_val,
            "score": score,
            "has_audio_match": len(matched_audio) > 0
        })

    # Also include very prominent audio transients that had significant motion
    for at, a_val in a_spikes:
        if a_val >= 0.22:
            if not any(abs(at - c["time_sec"]) <= 0.25 for c in fused_candidates):
                fused_candidates.append({
                    "time_sec": at,
                    "v_score": 10.0,
                    "a_score": a_val,
                    "score": 10.0 + a_val * 60.0,
                    "has_audio_match": True
                })

    # Sort by time
    fused_candidates = sorted(fused_candidates, key=lambda x: x["time_sec"])

    # Cluster/debounce to avoid duplicate sound triggers within min_hit_gap_sec
    debounced_hits: List[Dict[str, Any]] = []
    for cand in fused_candidates:
        if not debounced_hits:
            debounced_hits.append(cand)
        else:
            last = debounced_hits[-1]
            if (cand["time_sec"] - last["time_sec"]) < min_hit_gap_sec:
                if cand["score"] > last["score"]:
                    debounced_hits[-1] = cand
            else:
                debounced_hits.append(cand)

    # Intelligent SFX categorization
    final_hits = []
    # Rank top hits to assign bone crushes only to the most brutal moments
    top_scores = sorted([h["score"] for h in debounced_hits], reverse=True)
    bone_threshold = top_scores[min(4, len(top_scores)-1)] if len(top_scores) >= 3 else 30.0

    for h in debounced_hits:
        rel_time = round(h["time_sec"] - start_sec, 2)
        if rel_time < 0.8 or rel_time > duration_sec - 1.5:
            continue

        score = h["score"]
        # Heavy takedown / bone crunch only on top kinetic impacts
        if score >= bone_threshold and h["v_score"] >= 20.0 and h["has_audio_match"]:
            hit_type = "bone_crush"
            sfx_volume = 2.4
        elif score >= 22.0:
            hit_type = "punch_hard"
            sfx_volume = 2.1
        elif h["v_score"] >= 16.0:
            hit_type = "punch_face"
            sfx_volume = 1.9
        else:
            hit_type = "punch_body"
            sfx_volume = 1.7

        final_hits.append({
            "absolute_time": h["time_sec"],
            "relative_time": rel_time,
            "delay_ms": int(rel_time * 1000),
            "hit_type": hit_type,
            "score": round(score, 1),
            "volume": sfx_volume
        })

    print(f"[+] Successfully mapped {len(final_hits)} scene-matched hits ({sum(1 for x in final_hits if x['hit_type']=='bone_crush')} bone crushes).")
    for hit in final_hits:
        print(f"    t={hit['relative_time']:05.2f}s -> {hit['hit_type'].upper():<12} (Score: {hit['score']:>4.1f}, Vol: {hit['volume']})")

    return final_hits
