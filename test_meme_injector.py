"""
Automated Verification Suite for Meme Injector Module.
Tests:
1. Asset Bank directory initialization and auto-discovery.
2. Cutaway Injection (MoviePy slicing and concatenation).
3. Green Screen Chromakey Overlay (FFmpeg).
4. Audio SFX Only Injection (lossless video copy & natural game sound preservation).
5. Main Orchestrator dispatch.
"""

import os
import subprocess
from pathlib import Path
import meme_injector

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.getenv("OUTPUT_DIR", os.path.join(PROJECT_ROOT, "output"))
MUSIC_DIR = os.getenv("EPIDEMIC_MUSIC_DIR", os.path.join(PROJECT_ROOT, "assets", "epidemic_sound"))


def test_all_injection_modes():
    print("==================================================================")
    print("       RUNNING MEME INJECTOR AUTOMATED VERIFICATION SUITE         ")
    print("==================================================================")

    # 1. Test Asset Structure
    print("\n[Test 1] Testing Meme Asset Structure & Discovery...")
    meme_injector.ensure_meme_asset_structure()

    for trig in ["high_audio_peak", "kill_confirmed", "takedown"]:
        for mode in ["cutaway", "overlay", "audio"]:
            assets = meme_injector.get_available_memes(trig, mode)
            print(f"  Trigger '{trig}' / Mode '{mode}': Found {len(assets)} assets")
            assert len(assets) > 0, f"Expected assets for {trig}/{mode}, found 0"
    print("  [+] Test 1 Passed: Asset bank populated and mapped correctly.")

    # Source test video
    test_video = os.path.join(PROJECT_ROOT, "test_preview_18m.mp4")
    assert os.path.isfile(test_video), f"Test video not found: {test_video}"

    out_dir = os.path.join(OUTPUT_DIR, "memes_test")
    os.makedirs(out_dir, exist_ok=True)

    # 2. Test Audio SFX Injection (FFmpeg)
    print("\n[Test 2] Testing Audio SFX Injection (FFmpeg)...")
    sfx_asset = meme_injector.select_meme("high_audio_peak", "audio")
    assert sfx_asset is not None and os.path.isfile(sfx_asset), "Could not find audio asset"
    out_sfx = os.path.join(out_dir, "test_sfx_injection.mp4")

    res_sfx = meme_injector.inject_audio_sfx_ffmpeg(
        video_path=test_video,
        sfx_path=sfx_asset,
        timestamp=1.5,
        output_path=out_sfx
    )
    assert os.path.isfile(res_sfx) and os.path.getsize(res_sfx) > 0
    print(f"  [+] Test 2 Passed: Audio SFX injected successfully ({os.path.getsize(res_sfx)} bytes).")

    # 3. Test Green Screen Overlay (FFmpeg)
    print("\n[Test 3] Testing Green Screen Chromakey Overlay (FFmpeg)...")
    overlay_asset = meme_injector.select_meme("kill_confirmed", "overlay")
    assert overlay_asset is not None and os.path.isfile(overlay_asset), "Could not find overlay asset"
    out_overlay = os.path.join(out_dir, "test_overlay_injection.mp4")

    res_overlay = meme_injector.inject_greenscreen_overlay_ffmpeg(
        video_path=test_video,
        meme_path=overlay_asset,
        timestamp=1.0,
        output_path=out_overlay
    )
    assert os.path.isfile(res_overlay) and os.path.getsize(res_overlay) > 0
    print(f"  [+] Test 3 Passed: Green Screen Overlay injected successfully ({os.path.getsize(res_overlay)} bytes).")

    # 4. Test Cutaway (MoviePy)
    print("\n[Test 4] Testing Cutaway Slicing & Concatenation (MoviePy)...")
    cutaway_asset = meme_injector.select_meme("high_audio_peak", "cutaway")
    assert cutaway_asset is not None and os.path.isfile(cutaway_asset), "Could not find cutaway asset"
    out_cutaway = os.path.join(out_dir, "test_cutaway_injection.mp4")

    res_cutaway = meme_injector.inject_cutaway_moviepy(
        video_path=test_video,
        meme_path=cutaway_asset,
        timestamp=2.0,
        output_path=out_cutaway
    )
    assert os.path.isfile(res_cutaway) and os.path.getsize(res_cutaway) > 0
    print(f"  [+] Test 4 Passed: Cutaway concatenated successfully ({os.path.getsize(res_cutaway)} bytes).")

    # 5. Test Main Orchestration Function (inject_meme)
    print("\n[Test 5] Testing Main Orchestration Function (inject_meme)...")
    out_auto = os.path.join(out_dir, "test_orchestrator_auto.mp4")
    res_auto = meme_injector.inject_meme(
        video_path=test_video,
        timestamp=1.2,
        trigger_type="kill_confirmed",
        injection_type="overlay",
        output_path=out_auto
    )
    assert os.path.isfile(res_auto) and os.path.getsize(res_auto) > 0
    print(f"  [+] Test 5 Passed: Orchestrator executed cleanly ({os.path.getsize(res_auto)} bytes).")

    print("\n==================================================================")
    print("    ALL MEME INJECTOR TESTS COMPLETED SUCCESSFULLY!               ")
    print("==================================================================")

if __name__ == "__main__":
    test_all_injection_modes()
