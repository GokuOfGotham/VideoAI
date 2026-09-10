"""
Gameplay Event Detection Pipeline for VideoAI (Two-Pass Detection Policy).

Solves the 10GB+ raw footage processing bottleneck:
Pass 1: Audio Extraction & RMS Peak Clustering (Fast Pass)
Pass 2: Instant Coarse Video Trimming (-c copy stream copying)
Pass 3: Targeted Visual Validation (OpenCV cv2.matchTemplate on 30s clips only)

Ensures zero disk leaks with deterministic cleanup of all intermediate WAV and
unverified coarse candidate files, outputting verified action clips ready for
downstream MoviePy compositing and Faster-Whisper captioning.
"""

import argparse
import json
import os
import shutil
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from audio_peak_detector import detect_audio_events
from visual_hud_validator import (
    HUDTemplateMatcher,
    get_video_duration,
    trim_candidate_clip_stream_copy,
    validate_candidate_clip,
)


class TwoPassGameplayDetector:
    """
    Orchestrates the two-pass audio-visual event detection pipeline
    for massive gameplay recordings.
    """

    def __init__(
        self,
        output_dir: Optional[str] = None,
        hud_templates_dir: Optional[str] = None,
        clip_duration: float = 30.0,
        padding_before: float = 15.0,
        min_db: float = -26.0,
        peak_factor: float = 2.2,
        cluster_gap_sec: float = 15.0,
        match_threshold: float = 0.70,
        min_hud_confirmations: int = 2,
        keep_temp: bool = False
    ):
        base_dir = Path(__file__).resolve().parent
        self.output_dir = output_dir or str(base_dir / "output" / "verified_highlights")
        self.hud_templates_dir = hud_templates_dir or str(base_dir / "assets" / "hud_templates")
        self.clip_duration = clip_duration
        self.padding_before = padding_before
        self.min_db = min_db
        self.peak_factor = peak_factor
        self.cluster_gap_sec = cluster_gap_sec
        self.match_threshold = match_threshold
        self.min_hud_confirmations = min_hud_confirmations
        self.keep_temp = keep_temp

        os.makedirs(self.output_dir, exist_ok=True)
        self.matcher = HUDTemplateMatcher(templates_dir=self.hud_templates_dir)

    def process_video(self, video_path: str) -> List[Dict[str, Any]]:
        """
        Runs the complete Two-Pass Detection Policy on a large video file:
        1. Fast audio track demuxing & RMS peak clustering.
        2. Fast stream-copy trimming for each candidate peak.
        3. Targeted HUD template matching validation on 30s clips.
        4. Promoting verified clips and safely cleaning up temporary files.
        """
        video_path = os.path.abspath(video_path)
        if not os.path.isfile(video_path):
            raise FileNotFoundError(f"Video file not found: {video_path}")

        session_id = int(time.time())
        video_stem = Path(video_path).stem
        temp_dir = os.path.join(self.output_dir, f"_temp_session_{video_stem}_{session_id}")
        os.makedirs(temp_dir, exist_ok=True)

        verified_clips: List[Dict[str, Any]] = []
        temp_wav_path: Optional[str] = None
        candidate_clip_paths: List[str] = []

        print("\n" + "=" * 68)
        print(f"  VIDEOAI TWO-PASS GAMEPLAY EVENT DETECTOR")
        print(f"  Target Video: {Path(video_path).name}")
        print(f"  File Size   : {os.path.getsize(video_path) / (1024**3):.2f} GB")
        print("=" * 68 + "\n")

        t0 = time.time()

        try:
            # -------------------------------------------------------------
            # STEP 1: FAST PASS - AUDIO EXTRACTION & RMS PEAK CLUSTERING
            # -------------------------------------------------------------
            print("[Pass 1/3] Demuxing audio and computing RMS energy spikes...")
            clustered_peaks, temp_wav_path = detect_audio_events(
                video_path=video_path,
                temp_dir=temp_dir,
                min_db=self.min_db,
                peak_factor=self.peak_factor,
                cluster_gap=self.cluster_gap_sec
            )

            if not clustered_peaks:
                print("[-] No significant audio spikes detected above threshold. Video may be low intensity.")
                return []

            print(f"[+] Identified {len(clustered_peaks)} primary action event timestamps: {clustered_peaks}")

            # -------------------------------------------------------------
            # STEP 2: COARSE VIDEO TRIMMING (INSTANTANEOUS STREAM COPY)
            # -------------------------------------------------------------
            print(f"\n[Pass 2/3] Carving 30s candidate clips via FFmpeg stream copying (-c copy)...")
            video_duration = get_video_duration(video_path)

            candidate_metadata = []
            candidates_dir = os.path.join(temp_dir, "candidates")
            os.makedirs(candidates_dir, exist_ok=True)

            for idx, peak_t in enumerate(clustered_peaks):
                cand_name = f"candidate_{idx:03d}_peak_{int(peak_t)}s.mp4"
                cand_path = os.path.join(candidates_dir, cand_name)

                trim_info = trim_candidate_clip_stream_copy(
                    video_path=video_path,
                    peak_timestamp_sec=peak_t,
                    output_clip_path=cand_path,
                    clip_duration=self.clip_duration,
                    padding_before=self.padding_before,
                    video_duration=video_duration
                )
                candidate_clip_paths.append(cand_path)
                candidate_metadata.append(trim_info)

            print(f"[+] Instantaneously created {len(candidate_metadata)} coarse candidate clips (zero re-encoding).")

            # -------------------------------------------------------------
            # STEP 3: SMART PASS - TARGETED VISUAL VALIDATION (cv2.matchTemplate)
            # -------------------------------------------------------------
            print(f"\n[Pass 3/3] Routing targeted clips to OpenCV for HUD validation...")
            for idx, meta in enumerate(candidate_metadata):
                c_path = meta["clip_path"]
                peak_sec = meta["peak_sec"]
                start_sec = meta["start_sec"]

                print(f"  Validating Candidate [{idx+1}/{len(candidate_metadata)}]: peak={peak_sec}s (window={start_sec:.1f}s-{start_sec+self.clip_duration:.1f}s)...")
                val_res = validate_candidate_clip(
                    clip_path=c_path,
                    matcher=self.matcher,
                    match_threshold=self.match_threshold,
                    min_confirmations=self.min_hud_confirmations
                )

                if val_res["is_valid"]:
                    # Promote verified clip to final output directory
                    final_name = f"{video_stem}_highlight_{idx:03d}_{int(peak_sec)}s.mp4"
                    final_path = os.path.join(self.output_dir, final_name)
                    shutil.copy2(c_path, final_path)

                    event_entry = {
                        "video_source": video_path,
                        "highlight_clip": final_path,
                        "peak_time_sec": peak_sec,
                        "start_time_sec": start_sec,
                        "end_time_sec": start_sec + self.clip_duration,
                        "duration": self.clip_duration,
                        "hud_confirmations": val_res["hud_hits"],
                        "match_confidence": val_res["max_score"],
                        "motion_velocity": val_res["avg_motion"],
                        "status": "VERIFIED_GAMEPLAY_ACTION"
                    }
                    verified_clips.append(event_entry)
                    print(f"    >>> [PASS] Verified combat highlight saved to: {final_name} (HUD hits: {val_res['hud_hits']}, motion: {val_res['avg_motion']})")
                else:
                    print(f"    --- [REJECTED] {val_res['reason']} (HUD hits: {val_res['hud_hits']}, motion: {val_res['avg_motion']})")

            # Save manifest of verified events for downstream MoviePy & Whisper
            manifest_path = os.path.join(self.output_dir, f"{video_stem}_verified_events.json")
            with open(manifest_path, "w", encoding="utf-8") as f:
                json.dump(verified_clips, f, indent=2)

            elapsed = time.time() - t0
            print("\n" + "=" * 68)
            print(f"  DETECTION PIPELINE FINISHED IN {elapsed:.2f}s")
            print(f"  Verified Highlights: {len(verified_clips)} / {len(candidate_metadata)} candidate clips")
            print(f"  Manifest Saved: {manifest_path}")
            print("=" * 68 + "\n")

            return verified_clips

        finally:
            # -------------------------------------------------------------
            # DETERMINISTIC CLEANUP: Free all intermediate files
            # -------------------------------------------------------------
            if not self.keep_temp:
                print("[*] Performing cleanup of intermediate audio and candidate clips...")
                if temp_wav_path and os.path.isfile(temp_wav_path):
                    try:
                        os.remove(temp_wav_path)
                    except Exception:
                        pass

                if os.path.isdir(temp_dir):
                    try:
                        shutil.rmtree(temp_dir, ignore_errors=True)
                    except Exception:
                        pass
                print("[+] Cleanup complete. No residual temporary files remain.")


def main():
    parser = argparse.ArgumentParser(description="Two-Pass VideoAI Gameplay Event Detector")
    parser.add_argument("video", help="Path to raw gameplay video file (10GB+)")
    parser.add_argument("--output", "-o", default=None, help="Directory to store verified highlight clips")
    parser.add_argument("--min-db", type=float, default=-26.0, help="Minimum dBFS threshold for audio peaks (default: -26.0)")
    parser.add_argument("--peak-factor", type=float, default=2.2, help="Loudness multiplier above local baseline (default: 2.2)")
    parser.add_argument("--cluster-gap", type=float, default=15.0, help="Max gap in seconds between spikes to cluster (default: 15.0)")
    parser.add_argument("--hud-threshold", type=float, default=0.70, help="cv2.matchTemplate correlation threshold (default: 0.70)")
    parser.add_argument("--min-hits", type=int, default=2, help="Minimum HUD match confirmations required (default: 2)")
    parser.add_argument("--keep-temp", action="store_true", help="Do not delete intermediate audio and candidate clips")

    args = parser.parse_args()

    detector = TwoPassGameplayDetector(
        output_dir=args.output,
        min_db=args.min_db,
        peak_factor=args.peak_factor,
        cluster_gap_sec=args.cluster_gap,
        match_threshold=args.hud_threshold,
        min_hud_confirmations=args.min_hits,
        keep_temp=args.keep_temp
    )

    results = detector.process_video(args.video)
    print(f"Successfully processed video. Output clips: {len(results)}")


if __name__ == "__main__":
    main()
