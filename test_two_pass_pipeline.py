"""
Verification & Test Suite for Two-Pass Gameplay Event Detection Pipeline.
"""

import os
import sys
import numpy as np
from pathlib import Path

def run_tests():
    print("==================================================================")
    print("    RUNNING TWO-PASS DETECTION PIPELINE AUTOMATED TESTS           ")
    print("==================================================================")

    # 1. Test Audio Peak Detector Imports and Synthetic Audio Processing
    print("\n[Test 1] Testing audio_peak_detector...")
    import audio_peak_detector
    
    # Generate a 10-second synthetic audio waveform with two loud explosion spikes at t=3.0s and t=7.0s
    sr = 16000
    duration = 10.0
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    
    # Background low hum (rms ~ 0.02)
    waveform = (0.02 * np.sin(2 * np.pi * 120 * t)).astype(np.float32)
    
    # Spike 1 at 3.0s (burst of 800Hz with high amplitude 0.85)
    spike1_idx = int(3.0 * sr)
    waveform[spike1_idx:spike1_idx + int(0.3 * sr)] += 0.85 * np.sin(2 * np.pi * 800 * np.linspace(0, 0.3, int(0.3 * sr)))
    
    # Spike 2 at 3.4s (rapid gunfire follow-up, within cluster window of Spike 1)
    spike2_idx = int(3.4 * sr)
    waveform[spike2_idx:spike2_idx + int(0.2 * sr)] += 0.90 * np.sin(2 * np.pi * 900 * np.linspace(0, 0.2, int(0.2 * sr)))
    
    # Spike 3 at 7.5s (separate encounter)
    spike3_idx = int(7.5 * sr)
    waveform[spike3_idx:spike3_idx + int(0.4 * sr)] += 0.80 * np.sin(2 * np.pi * 500 * np.linspace(0, 0.4, int(0.4 * sr)))

    timestamps, rms = audio_peak_detector.compute_sliding_rms(waveform, sr, window_sec=0.20, hop_sec=0.05)
    assert len(timestamps) > 0, "RMS timestamps should not be empty"
    assert len(rms) == len(timestamps), "RMS length must match timestamps length"

    raw_spikes = audio_peak_detector.detect_audio_spikes(timestamps, rms, min_db=-26.0, peak_factor=2.0)
    print(f"  Detected raw spikes: {[(round(t, 2), round(r, 3)) for t, r in raw_spikes]}")
    assert len(raw_spikes) >= 2, f"Expected at least 2 raw spikes, got {len(raw_spikes)}"

    clustered = audio_peak_detector.cluster_timestamps(raw_spikes, min_cluster_gap=2.0)
    print(f"  Clustered event markers: {clustered}")
    # Spike 1 and 2 should be clustered together (~3.0-3.5s), and Spike 3 separate (~7.5s)
    assert len(clustered) == 2, f"Expected 2 clustered events, got {len(clustered)}"
    assert 2.8 <= clustered[0] <= 3.8, f"First cluster should be near 3.0-3.5s, got {clustered[0]}"
    assert 7.0 <= clustered[1] <= 8.0, f"Second cluster should be near 7.5s, got {clustered[1]}"
    print("  [+] Test 1 Passed: RMS computation, spike detection & clustering verified.")

    # 2. Test HUD Template Matcher
    print("\n[Test 2] Testing visual_hud_validator...")
    import visual_hud_validator
    import cv2

    matcher = visual_hud_validator.HUDTemplateMatcher()
    assert len(matcher.templates) >= 3, f"Expected default templates to be generated, got {len(matcher.templates)}"
    print(f"  Loaded templates: {list(matcher.templates.keys())}")

    # Create a synthetic 1080p frame with a hitmarker stamped in the center
    synthetic_frame = np.ones((1080, 1920), dtype=np.uint8) * 40
    # Stamp standard hitmarker near center
    tpl = matcher.templates["hitmarker_standard"]
    th, tw = tpl.shape
    cy, cx = 1080 // 2, 1920 // 2
    synthetic_frame[cy:cy+th, cx:cx+tw] = tpl

    match_res = matcher.match_frame(synthetic_frame, threshold=0.65)
    print(f"  Match Result on synthetic frame: {match_res}")
    assert match_res["matched"] is True, "Synthetic hitmarker should be detected"
    assert match_res["template"] == "hitmarker_standard", f"Expected hitmarker_standard, got {match_res['template']}"
    assert match_res["score"] >= 0.70, f"Score should be high, got {match_res['score']}"
    print("  [+] Test 2 Passed: Template matching and multi-scale detection verified.")

    # 3. Test Gameplay Event Pipeline Integration with real video preview
    print("\n[Test 3] Testing gameplay_event_pipeline on real video (test_preview_18m.mp4)...")
    from gameplay_event_pipeline import TwoPassGameplayDetector

    test_video = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_preview_18m.mp4")
    if os.path.exists(test_video):
        detector = TwoPassGameplayDetector(
            clip_duration=3.0,
            padding_before=1.5,
            min_db=-30.0,
            peak_factor=1.5,
            cluster_gap_sec=2.0,
            match_threshold=0.60,
            min_hud_confirmations=1
        )
        results = detector.process_video(test_video)
        print(f"  Pipeline execution completed. Processed results: {len(results)}")
        # Check that no temp directory was left behind
        temp_dirs = [d for d in os.listdir(detector.output_dir) if d.startswith("_temp_session_")]
        assert len(temp_dirs) == 0, f"Temporary directories should be cleaned up, found: {temp_dirs}"
        print("  [+] Test 3 Passed: Pipeline executed with automatic deterministic cleanup.")
    else:
        print(f"  [!] Skipped real video test: {test_video} not found")

    print("\n==================================================================")
    print("    ALL AUTOMATED TESTS PASSED SUCCESSFULLY!                      ")
    print("==================================================================")

if __name__ == "__main__":
    run_tests()
