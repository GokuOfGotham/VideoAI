"""Fast combat-event scan of a long gameplay recording, audio first.

A 40 GB 4K recording cannot be decoded frame by frame in any useful time, but
its audio can: this reads only the audio stream in fixed windows, clusters the
loudness spikes into candidate fight moments, ranks every cluster across the
whole recording, and HUD-validates just the strongest with OpenCV. The result
is a JSON list of scored events with absolute timestamps that a producer can
cut from with stream-copy trims.

    python scan_longform_combat.py --video "M:/.../Arkham Knight (The Movie).mp4"
"""

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from audio_peak_detector import (  # noqa: E402
    cluster_timestamps,
    compute_sliding_rms,
    detect_audio_spikes,
    load_wav_samples,
)

DEFAULT_OUT = PROJECT_ROOT / "assets" / "materials" / "top10" / "movie_scan.json"


def _duration(video: str) -> float:
    res = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", video],
        capture_output=True, text=True, timeout=60,
    )
    return float(res.stdout.strip())


def _demux_audio_window(video: str, start: float, length: float, dest: Path) -> bool:
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-ss", f"{start:.2f}", "-t", f"{length:.2f}",
        "-i", video,
        "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le",
        str(dest),
    ]
    res = subprocess.run(cmd, capture_output=True, timeout=600)
    return res.returncode == 0 and dest.exists() and dest.stat().st_size > 32_000


def scan_audio(video: str, window: float, start: float, end: float, temp: Path) -> List[Dict[str, Any]]:
    """First pass: every loudness cluster in the recording, with its strength."""
    clusters: List[Dict[str, Any]] = []
    total_windows = int((end - start) // window) + 1
    t0 = time.time()

    for i in range(total_windows):
        w_start = start + i * window
        w_len = min(window, end - w_start)
        if w_len < 20:
            break

        wav = temp / f"win_{int(w_start)}.wav"
        ok = _demux_audio_window(video, w_start, w_len, wav)
        if not ok:
            print(f"  [{i + 1}/{total_windows}] t={int(w_start) // 60:>3}m  demux failed", flush=True)
            continue

        try:
            samples, sr = load_wav_samples(str(wav))
            ts, rms = compute_sliding_rms(samples, sr)
            ts = np.asarray(ts, dtype=float)
            rms = np.asarray(rms, dtype=float)
            spikes = detect_audio_spikes(ts, rms, min_db=-25.0, peak_factor=2.0)
            offsets = cluster_timestamps(spikes, min_cluster_gap=15.0)

            found = 0
            for off in offsets:
                near = (ts >= off - 6.0) & (ts <= off + 6.0)
                if not near.any():
                    continue
                strength = float(rms[near].max())
                density = int(sum(1 for s in spikes if abs(s - off) <= 8.0))
                clusters.append({
                    "peak_time_sec": round(w_start + float(off), 2),
                    "rms_peak": round(strength, 5),
                    "spike_density": density,
                    "audio_score": round(strength * (1.0 + 0.15 * density), 5),
                })
                found += 1

            elapsed = time.time() - t0
            print(f"  [{i + 1}/{total_windows}] t={int(w_start) // 60:>3}m  clusters={found:<2}  ({elapsed:.0f}s)", flush=True)
        finally:
            wav.unlink(missing_ok=True)

    return clusters


def validate_top(video: str, clusters: List[Dict[str, Any]], top_n: int, temp: Path) -> None:
    """Second pass: stream-copy the strongest candidates and check for combat HUD."""
    try:
        from visual_hud_validator import (
            HUDTemplateMatcher,
            trim_candidate_clip_stream_copy,
            validate_candidate_clip,
        )
        matcher = HUDTemplateMatcher()
    except Exception as exc:
        print(f"[scan] HUD validation unavailable ({exc}); audio ranking only.", flush=True)
        return

    ranked = sorted(clusters, key=lambda c: c["audio_score"], reverse=True)
    picked: List[Dict[str, Any]] = []
    for c in ranked:
        # Keep candidates spread out; two peaks in the same brawl are one event.
        if all(abs(c["peak_time_sec"] - p["peak_time_sec"]) >= 90.0 for p in picked):
            picked.append(c)
        if len(picked) >= top_n:
            break

    for n, c in enumerate(picked, 1):
        peak = c["peak_time_sec"]
        cand = temp / f"cand_{int(peak)}.mp4"
        try:
            trim_candidate_clip_stream_copy(
                video_path=video, peak_timestamp_sec=peak,
                output_clip_path=str(cand), clip_duration=30.0, padding_before=15.0,
            )
            val = validate_candidate_clip(str(cand), matcher=matcher,
                                          match_threshold=0.65, min_confirmations=1)
            c["hud_hits"] = int(val.get("hud_hits", 0))
            c["avg_motion"] = round(float(val.get("avg_motion", 0.0)), 2)
            c["is_valid"] = bool(val.get("is_valid", False))
            c["score"] = round(c["hud_hits"] * 1.5 + c["avg_motion"] + c["audio_score"] * 10, 3)
            h, m, s = int(peak // 3600), int(peak % 3600 // 60), int(peak % 60)
            print(f"  validate {n:>2}/{len(picked)}  {h:02d}:{m:02d}:{s:02d}  "
                  f"hud={c['hud_hits']:<3} motion={c['avg_motion']:<6} valid={c['is_valid']}", flush=True)
        except Exception as exc:
            print(f"  validate {n:>2}/{len(picked)}  t={peak:.0f}s  failed ({exc})", flush=True)
        finally:
            cand.unlink(missing_ok=True)


def main() -> int:
    ap = argparse.ArgumentParser(description="Audio-first combat scan of a long gameplay video")
    ap.add_argument("--video", required=True)
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--window", type=float, default=180.0, help="audio window in seconds")
    ap.add_argument("--start", type=float, default=0.0)
    ap.add_argument("--end", type=float, default=None)
    ap.add_argument("--validate-top", type=int, default=16, help="HUD-validate this many top clusters")
    args = ap.parse_args()

    video = args.video
    end = args.end or _duration(video)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    temp = out.parent / ".scan_tmp"
    temp.mkdir(parents=True, exist_ok=True)

    print(f"[scan] {Path(video).name}  {end / 3600:.2f}h  window={args.window:.0f}s", flush=True)
    clusters = scan_audio(video, args.window, args.start, end, temp)
    print(f"[scan] audio pass: {len(clusters)} clusters", flush=True)

    validate_top(video, clusters, args.validate_top, temp)

    clusters.sort(key=lambda c: c.get("score", c["audio_score"] * 10), reverse=True)
    payload = {
        "video": video,
        "duration_sec": end,
        "scanned_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "events": clusters,
    }
    with open(out, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=1)

    validated = [c for c in clusters if c.get("is_valid")]
    print(f"[scan] wrote {out}  ({len(clusters)} events, {len(validated)} HUD-validated)", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
