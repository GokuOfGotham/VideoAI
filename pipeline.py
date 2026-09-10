"""Automated MoneyPrinterTurbo-style Video Generation Pipeline for VideoAI.

Unifies script generation (LLM), local Voicebox GPU voice synthesis (James Earl Jones profile),
ASS animated subtitles, military/stock footage fetching, and FFmpeg 9:16 vertical rendering.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional
from dotenv import load_dotenv

from script_generator import generate_video_script
from voice_synthesizer import synthesize_narration, get_audio_duration
from subtitle_engine import create_ass_subtitles
from material_fetcher import fetch_material_for_scene

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", str(PROJECT_ROOT / "output")))
ASSETS_DIR = PROJECT_ROOT / "assets"

os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(ASSETS_DIR, exist_ok=True)


def build_automated_video(
    topic: str,
    target_duration: int = 30,
    voice_provider: str = "voicebox",
    voice_name: str = "James Earl Jones",
    llm_provider: str = "openai",
    font_name: str = "Impact",
    bgm_path: Optional[str] = None
) -> str:
    """Executes full automated video production pipeline using local Voicebox GPU voice synthesis."""
    timestamp_str = time.strftime("%Y%m%d_%H%M%S")
    clean_topic = re.sub(r"[^\w]", "_", topic.lower())[:20]
    output_video_path = str(OUTPUT_DIR / f"Short_{clean_topic}_{timestamp_str}.mp4")

    print(f"\n=======================================================")
    print(f"   VIDEOAI AUTOMATED PIPELINE: '{topic}'")
    print(f"=======================================================")

    # Step 1: Generate Script
    print("\n[Step 1/5] Generating LLM Script & Scene Director...")
    script = generate_video_script(topic, target_duration_seconds=target_duration, llm_provider=llm_provider)
    print(f"  Title: {script.get('title')}")
    print(f"  Narration: {script.get('narration_script')[:80]}...")
    print(f"  Scenes Count: {len(script.get('scenes', []))}")

    # Step 2: Local Voicebox GPU Voice Synthesis (James Earl Jones)
    print(f"\n[Step 2/5] Synthesizing Voiceover via Local Voicebox ({voice_name}) & Timing Alignment...")
    audio_path, duration, word_timestamps = synthesize_narration(
        script["narration_script"],
        output_filename=f"narration_{timestamp_str}.mp3",
        provider=voice_provider,
        voice=voice_name
    )
    print(f"  Audio File: {audio_path} ({duration:.2f}s)")
    print(f"  Words Timed: {len(word_timestamps)}")

    # Step 3: Create ASS Animated Subtitles (Large Centered TikTok Typography)
    print("\n[Step 3/5] Building ASS TikTok-Style Large Centered Subtitles...")
    ass_path = str(ASSETS_DIR / f"subtitles_{timestamp_str}.ass")
    create_ass_subtitles(
        word_timestamps,
        ass_path,
        font_name=font_name,
        font_size=68,        # Large 68pt text for 1080x1920
        words_per_caption=2, # Fast 2-word TikTok retention cadence
        alignment=5,         # 5 = Mid-Center Focal Zone
        vertical_margin=0
    )
    print(f"  ASS File: {ass_path}")

    # Step 4: Fetch Material Video Clips for Scenes
    print("\n[Step 4/5] Sourcing Media Footage for Scenes...")
    scene_clips = []
    scenes = script.get("scenes", [])
    if not scenes:
        scenes = [{"search_keywords": topic, "duration_est": duration}]

    scene_dur = duration / len(scenes)

    for idx, sc in enumerate(scenes):
        kw = sc.get("search_keywords", topic)
        print(f"  Scene {idx+1}/{len(scenes)}: searching '{kw}'...")
        clip = fetch_material_for_scene(kw, target_duration=scene_dur)
        if clip:
            scene_clips.append(clip)
            print(f"    -> Using: {Path(clip).name}")
        else:
            print(f"    -> Warning: No clip found for '{kw}'")

    if not scene_clips:
        raise RuntimeError("Failed to source media clips for video rendering.")

    # Step 5: Render Final 9:16 Vertical Video via FFmpeg
    print("\n[Step 5/5] Assembling & Rendering Final Vertical Video (9:16)...")
    _render_ffmpeg_vertical(
        video_clips=scene_clips,
        audio_path=audio_path,
        ass_path=ass_path,
        output_path=output_video_path,
        total_duration=duration,
        bgm_path=bgm_path
    )

    print(f"\n=======================================================")
    print(f"   SUCCESS! Rendered video saved to:")
    print(f"   {output_video_path}")
    print(f"=======================================================\n")

    return output_video_path


def _render_ffmpeg_vertical(
    video_clips: List[str],
    audio_path: str,
    ass_path: str,
    output_path: str,
    total_duration: float,
    bgm_path: Optional[str] = None
):
    """Renders 9:16 vertical video with combined video clips, audio, and ASS subtitles."""
    escaped_ass = ass_path.replace("\\", "/").replace(":", "\\:")

    inputs = []
    filter_parts = []

    for i, clip in enumerate(video_clips):
        inputs.extend(["-i", clip])
        filter_parts.append(
            f"[{i}:v]scale=1080:1920:force_original_aspect_ratio=increase,"
            f"crop=1080:1920,setsar=1,fps=30[v{i}];"
        )

    concat_inputs = "".join(f"[v{i}]" for i in range(len(video_clips)))
    filter_parts.append(f"{concat_inputs}concat=n={len(video_clips)}:v=1:a=0[vconcat];")
    filter_parts.append(f"[vconcat]ass='{escaped_ass}'[vfinal]")

    filter_complex = "".join(filter_parts)

    cmd = [
        "ffmpeg", "-y",
        *inputs,
        "-i", audio_path,
        "-filter_complex", filter_complex,
        "-map", "[vfinal]",
        "-map", f"{len(video_clips)}:a",
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "22",
        "-c:a", "aac",
        "-b:a", "192000",
        "-t", str(total_duration),
        "-pix_fmt", "yuv420p",
        output_path
    ]

    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError as exc:
        print(f"[Pipeline] FFmpeg rendering error:\n{exc.stderr[-1000:]}")
        raise RuntimeError("FFmpeg rendering failed.")


def main():
    parser = argparse.ArgumentParser(description="Automated VideoAI Short-Form Video Generator")
    parser.add_argument("--topic", type=str, default="Ukraine vs Russia Tactical Shift and Drone Warfare", help="Video topic or prompt")
    parser.add_argument("--duration", type=int, default=25, help="Target video duration in seconds")
    parser.add_argument("--voice", type=str, default="voicebox", choices=["voicebox", "edge", "openai", "elevenlabs"], help="TTS voice provider")
    parser.add_argument("--voice-name", type=str, default="James Earl Jones", help="Voice profile name for Voicebox")
    parser.add_argument("--llm", type=str, default="openai", choices=["openai", "gemini", "deepseek"], help="LLM provider")

    args = parser.parse_args()
    build_automated_video(
        topic=args.topic,
        target_duration=args.duration,
        voice_provider=args.voice,
        voice_name=args.voice_name,
        llm_provider=args.llm
    )


if __name__ == "__main__":
    main()
