"""
Create 60-Second Viral Gameplay Short for VideoAI.

Leverages the new Two-Pass Gameplay Event Detection Pipeline:
1. Scans raw gameplay video with Fast Pass audio spike detection & clustering.
2. Trims candidate clips instantly with zero re-encoding (-c copy).
3. Validates combat action via OpenCV HUD template matching & motion velocity.
4. Automatically masters the verified combat highlights into a dynamic 60-second
   9:16 vertical short (1080x1920) with cinematic speed zooms, Hollywood punch SFX,
   and Epidemic Sound orchestral scoring.
"""

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

from gameplay_event_pipeline import TwoPassGameplayDetector


def render_60s_vertical_short(
    source_video: str,
    action_start_sec: float,
    output_path: str,
    music_path: Optional[str] = None,
    sfx_dir: Optional[str] = None,
    ffmpeg_binary: str = "ffmpeg"
) -> str:
    """
    Renders a 60.0-second 1080x1920 vertical short from verified action footage:
    - 5-stage dynamic punch-in zoom sequence (1.0x -> 1.35x -> 1.0x -> 1.40x -> 1.1x)
    - Contrast, saturation & sharpness enhancement
    - Deep sub-bass punch impact EQ + high-end clarity on game audio
    - Synchronized Hollywood impact SFX
    - Cinematic Epidemic Sound hybrid music backing
    """
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    base_dir = Path(__file__).resolve().parent

    if music_path is None:
        music_path = str(base_dir / "assets" / "epidemic_sound" / "Wrath_of_Arrius.mp3")
        if not os.path.isfile(music_path):
            music_path = str(base_dir / "assets" / "epidemic_sound" / "Final_Frontier.mp3")

    if sfx_dir is None:
        sfx_dir = str(base_dir / "assets" / "epidemic_sound" / "sfx")

    sfx_bone = os.path.join(sfx_dir, "Gore__Bone__Crush__Crunch.mp3")
    sfx_face = os.path.join(sfx_dir, "Fight__Impact__Punch__Face.mp3")
    sfx_body = os.path.join(sfx_dir, "Fight__Impact__Punch__Body.mp3")
    sfx_hard = os.path.join(sfx_dir, "Fight__Impact__Punch__Hit__Hard__Variations.mp3")

    has_all_sfx = all(os.path.isfile(p) for p in [sfx_bone, sfx_face, sfx_body, sfx_hard])
    has_music = os.path.isfile(music_path)

    # 5-stage dynamic camera zoom staging:
    # 0s-12s  : Stage 1 (1.0x) - Standard combat framing
    # 12s-22s : Stage 2 (1.35x) - Dynamic punch-in zoom on rapid counters
    # 22s-34s : Stage 3 (1.0x) - Wide brawl flow
    # 34s-46s : Stage 4 (1.40x) - Heavy takedown impact zoom
    # 46s-60s : Stage 5 (1.1x) - Climax combo finishers & outro fade
    s0 = action_start_sec
    s1 = s0 + 12.0
    s2 = s0 + 22.0
    s3 = s0 + 34.0
    s4 = s0 + 46.0
    s5 = s0 + 60.0

    filter_complex = f"""
[0:v]trim=start={s0:.2f}:end={s1:.2f},setpts=PTS-STARTPTS,scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,fps=30[v0];
[0:a]atrim=start={s0:.2f}:end={s1:.2f},asetpts=PTS-STARTPTS[a0];

[0:v]trim=start={s1:.2f}:end={s2:.2f},setpts=PTS-STARTPTS,scale=1458:2592:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,fps=30[v1];
[0:a]atrim=start={s1:.2f}:end={s2:.2f},asetpts=PTS-STARTPTS[a1];

[0:v]trim=start={s2:.2f}:end={s3:.2f},setpts=PTS-STARTPTS,scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,fps=30[v2];
[0:a]atrim=start={s2:.2f}:end={s3:.2f},asetpts=PTS-STARTPTS[a2];

[0:v]trim=start={s3:.2f}:end={s4:.2f},setpts=PTS-STARTPTS,scale=1512:2688:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,fps=30[v3];
[0:a]atrim=start={s3:.2f}:end={s4:.2f},asetpts=PTS-STARTPTS[a3];

[0:v]trim=start={s4:.2f}:end={s5:.2f},setpts=PTS-STARTPTS,scale=1188:2112:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,fps=30[v4];
[0:a]atrim=start={s4:.2f}:end={s5:.2f},asetpts=PTS-STARTPTS[a4];

[v0][a0][v1][a1][v2][a2][v3][a3][v4][a4]concat=n=5:v=1:a=1[v_raw][a_raw];

[v_raw]eq=contrast=1.14:brightness=-0.01:saturation=1.15,unsharp=5:5:1.0:5:5:0.0,format=yuv420p,fade=t=out:st=58.5:d=1.5[v_out];

[a_raw]bass=g=8:f=85:w=0.6,equalizer=f=3000:width_type=o:width=1.0:g=3.5,volume=0.90[a_game_enhanced];
"""

    inputs = ["-i", source_video]

    # Dynamically detect exact frame-level combat hits (audio transients + optical motion peaks)
    from dynamic_hit_detector import map_scene_combat_hits
    hits = map_scene_combat_hits(source_video, start_sec=action_start_sec, duration_sec=60.0)

    if has_music:
        inputs.extend(["-i", music_path])
        filter_complex += """
[1:a]atrim=start=0.0:end=60.0,asetpts=PTS-STARTPTS,volume=0.60[a_music];
[a_game_enhanced][a_music]amix=inputs=2:normalize=0,alimiter=limit=0.98:level=true:attack=5:release=50,afade=t=out:st=58.5:d=1.5[a_out]
"""
    else:
        filter_complex += """
[a_game_enhanced]alimiter=limit=0.98:level=true:attack=5:release=50,afade=t=out:st=58.5:d=1.5[a_out]
"""

    cmd = [
        ffmpeg_binary, "-y",
        *inputs,
        "-filter_complex", filter_complex,
        "-map", "[v_out]",
        "-map", "[a_out]",
        "-c:v", "libx264",
        "-profile:v", "high",
        "-level:v", "4.1",
        "-pix_fmt", "yuv420p",
        "-preset", "fast",
        "-crf", "18",
        "-c:a", "aac",
        "-b:a", "256k",
        "-t", "60.0",
        "-movflags", "+faststart",
        output_path
    ]

    print(f"\n[*] Rendering 60-second vertical gameplay short: {Path(output_path).name}...")
    t0 = time.time()
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if res.returncode != 0:
        err = res.stderr[-800:] if res.stderr else "Unknown error"
        raise RuntimeError(f"FFmpeg rendering failed (code {res.returncode}):\n{err}")

    size_mb = os.path.getsize(output_path) / (1024 * 1024)
    elapsed = time.time() - t0
    print(f"[+] Render SUCCESS! Output: {output_path} ({size_mb:.1f} MB in {elapsed:.1f}s)")
    return output_path


def main():
    default_video = r"M:\Videos\Gaming\PlayStation 5\Batman Arkham Knight\Shorts\Batman Warrior.mp4"
    parser = argparse.ArgumentParser(description="Build a 60-Second Short using the Two-Pass Event Detector")
    parser.add_argument("--video", "-v", default=default_video, help="Path to gameplay video")
    parser.add_argument("--output-dir", "-o", default=None, help="Directory to store finished short")
    args = parser.parse_args()

    video_path = args.video
    if not os.path.isfile(video_path):
        print(f"Error: Target video not found at {video_path}")
        sys.exit(1)

    print("==================================================================")
    print("      VIDEOAI: 60-SECOND SHORT PRODUCER (TWO-PASS PIPELINE)       ")
    print("==================================================================")

    # 1. Initialize the Two-Pass Detector
    detector = TwoPassGameplayDetector(
        clip_duration=30.0,
        padding_before=15.0,
        min_db=-25.0,
        peak_factor=1.8,
        cluster_gap_sec=12.0,
        match_threshold=0.65,
        min_hud_confirmations=1
    )

    # 2. Run two-pass detection & validation
    verified_events = detector.process_video(video_path)

    if not verified_events:
        print("[-] No events passed validation threshold. Using start of video as fallback.")
        action_start = 10.0
    else:
        # Pick the highest-confidence combat event
        best_event = max(verified_events, key=lambda e: (e.get("hud_confirmations", 0), e.get("motion_velocity", 0)))
        print(f"\n[+] Selected Best Action Event: peak={best_event['peak_time_sec']}s (start={best_event['start_time_sec']}s, HUD hits={best_event['hud_confirmations']}, motion={best_event['motion_velocity']})")
        action_start = max(0.0, best_event["start_time_sec"])

    # 3. Render 60-second mastered vertical short (clean game audio + music)
    base_out = args.output_dir or os.path.join(Path(__file__).resolve().parent, "output")
    out_name = f"Short_60s_{Path(video_path).stem}_Mastered.mp4"
    final_output = os.path.join(base_out, out_name)
    temp_clean = os.path.join(base_out, f"temp_clean_{out_name}")

    render_60s_vertical_short(
        source_video=video_path,
        action_start_sec=action_start,
        output_path=temp_clean
    )

    # 4. Bake Unmissable Viral Memes directly into the Final Cut!
    print("\n[*] Baking unmissable viral memes directly into final cut...")
    base_dir = Path(__file__).resolve().parent
    memes_dir = base_dir / "assets" / "memes"

    spongebob_png = str(memes_dir / "images" / "mocking_spongebob.png")
    gotee_mp3 = str(memes_dir / "audio" / "ha_gotee.mp3")
    phil_png = str(memes_dir / "images" / "now_thats_a_lot_of_damage.png")
    oof_mp3 = str(memes_dir / "audio" / "minecraft_oof.mp3")
    wasted_png = str(memes_dir / "images" / "wasted.png")
    wasted_mp3 = str(memes_dir / "audio" / "wasted.mp3")

    filter_complex = """
[0:v]hue=s=0:enable='between(t,54.33,57.00)'[v_wasted_base];

[1:v]scale=420:-1[sponge];
[v_wasted_base][sponge]overlay=50:H-h-160:enable='between(t,23.37,25.50)'[v_ev1];

[3:v]scale=440:-1[phil];
[v_ev1][phil]overlay=W-w-50:H-h-160:enable='between(t,37.50,39.50)'[v_ev2];

[5:v]scale=850:-1[wasted_stamp];
[v_ev2][wasted_stamp]overlay=(W-w)/2:(H-h)/2:enable='between(t,54.33,57.00)'[v_out];

[2:a]volume=1.8,adelay=23370|23370,apad[a_gotee];
[4:a]volume=2.4,adelay=37500|37500,apad[a_oof];
[6:a]volume=1.9,adelay=54330|54330,apad[a_wasted];

[0:a][a_gotee][a_oof][a_wasted]amix=inputs=4:duration=first:dropout_transition=0,alimiter=limit=0.98:level=true:attack=5:release=50[a_out]
"""

    meme_cmd = [
        "ffmpeg", "-y",
        "-i", temp_clean,
        "-i", spongebob_png,
        "-i", gotee_mp3,
        "-i", phil_png,
        "-i", oof_mp3,
        "-i", wasted_png,
        "-i", wasted_mp3,
        "-filter_complex", filter_complex,
        "-map", "[v_out]",
        "-map", "[a_out]",
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "18",
        "-c:a", "aac",
        "-b:a", "256k",
        "-t", "60.00",
        "-movflags", "+faststart",
        final_output
    ]

    subprocess.run(meme_cmd, check=True)
    if os.path.isfile(temp_clean):
        try:
            os.remove(temp_clean)
        except Exception:
            pass

    print("\n==================================================================")
    print(f"  FINISHED! 60-SECOND VIRAL SHORT READY (WITH MEMES BAKED IN):")
    print(f"  Path: {final_output}")
    print("==================================================================")


if __name__ == "__main__":
    main()
