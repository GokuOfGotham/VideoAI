"""
Meme Injector Module for VideoAI.

Dynamically inserts memes at key gameplay moments (e.g., high audio peaks,
kill confirmations, takedowns, headshots) using three distinct injection modes:
1. Cutaway (MoviePy): Slices video at timestamp, inserts meme clip, concatenates.
2. Green Screen Overlay (FFmpeg): Chromakeys green background (0x00FF00) and overlays on gameplay.
3. Audio SFX Only (FFmpeg/MoviePy): Mixes sound effect at exact timestamp while preserving natural game audio.

Audio Constraint:
Strictly preserves natural in-game audio and injects ONLY the specific meme sound.
Never introduces unrequested background music or radio chatter.
"""

import argparse
import glob
import os
import random
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np
from moviepy import AudioFileClip, CompositeAudioClip, VideoFileClip, concatenate_videoclips


# ==============================================================================
# 1. ASSET BANK & TRIGGER MAPPING
# ==============================================================================

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_MEMES_DIR = BASE_DIR / "assets" / "memes"

TRIGGER_ASSET_MAP = {
    "high_audio_peak": {
        "cutaway": str(DEFAULT_MEMES_DIR / "cutaway" / "high_audio_peak"),
        "overlay": str(DEFAULT_MEMES_DIR / "overlay" / "high_audio_peak"),
        "audio": str(DEFAULT_MEMES_DIR / "audio" / "high_audio_peak"),
    },
    "kill_confirmed": {
        "cutaway": str(DEFAULT_MEMES_DIR / "cutaway" / "kill_confirmed"),
        "overlay": str(DEFAULT_MEMES_DIR / "overlay" / "kill_confirmed"),
        "audio": str(DEFAULT_MEMES_DIR / "audio" / "kill_confirmed"),
    },
    "takedown": {
        "cutaway": str(DEFAULT_MEMES_DIR / "cutaway" / "takedown"),
        "overlay": str(DEFAULT_MEMES_DIR / "overlay" / "takedown"),
        "audio": str(DEFAULT_MEMES_DIR / "audio" / "takedown"),
    },
    "headshot": {
        "cutaway": str(DEFAULT_MEMES_DIR / "cutaway" / "headshot"),
        "overlay": str(DEFAULT_MEMES_DIR / "overlay" / "headshot"),
        "audio": str(DEFAULT_MEMES_DIR / "audio" / "headshot"),
    },
    "general": {
        "cutaway": str(DEFAULT_MEMES_DIR / "cutaway"),
        "overlay": str(DEFAULT_MEMES_DIR / "overlay"),
        "audio": str(DEFAULT_MEMES_DIR / "audio"),
    },
}


def ensure_meme_asset_structure(memes_dir: Optional[Path] = None):
    """
    Ensures the meme folder hierarchy exists and populates starter
    placeholders/SFX if folders are initially empty.
    """
    root = memes_dir or DEFAULT_MEMES_DIR
    subfolders = [
        root / "cutaway" / "high_audio_peak",
        root / "cutaway" / "kill_confirmed",
        root / "overlay" / "high_audio_peak",
        root / "overlay" / "kill_confirmed",
        root / "audio" / "high_audio_peak",
        root / "audio" / "kill_confirmed",
    ]
    for folder in subfolders:
        folder.mkdir(parents=True, exist_ok=True)

    # 1. Populate starter Audio SFX from existing project SFX if empty
    sfx_source_dir = BASE_DIR / "assets" / "epidemic_sound" / "sfx"
    audio_peak_dir = root / "audio" / "high_audio_peak"
    audio_kill_dir = root / "audio" / "kill_confirmed"

    if sfx_source_dir.is_dir():
        import shutil
        for sfx_file in sfx_source_dir.glob("*.mp3"):
            dest_peak = audio_peak_dir / sfx_file.name
            dest_kill = audio_kill_dir / sfx_file.name
            if not dest_peak.exists():
                shutil.copy2(sfx_file, dest_peak)
            if not dest_kill.exists():
                shutil.copy2(sfx_file, dest_kill)

    # 2. Generate starter Green Screen Overlay video if none exists
    overlay_sample = root / "overlay" / "kill_confirmed" / "sample_hitmarker_greenscreen.mp4"
    overlay_sample_peak = root / "overlay" / "high_audio_peak" / "sample_hitmarker_greenscreen.mp4"
    if not overlay_sample.exists():
        _generate_sample_greenscreen_clip(str(overlay_sample))
    if not overlay_sample_peak.exists():
        import shutil
        shutil.copy2(overlay_sample, overlay_sample_peak)

    # 3. Generate starter Cutaway video if none exists
    cutaway_sample = root / "cutaway" / "high_audio_peak" / "sample_dramatic_cutaway.mp4"
    cutaway_sample_kill = root / "cutaway" / "kill_confirmed" / "sample_dramatic_cutaway.mp4"
    if not cutaway_sample.exists():
        _generate_sample_cutaway_clip(str(cutaway_sample))
    if not cutaway_sample_kill.exists():
        import shutil
        shutil.copy2(cutaway_sample, cutaway_sample_kill)


def _generate_sample_greenscreen_clip(output_path: str, duration: float = 2.0, fps: int = 30):
    """Generates a synthetic green-screen (0x00FF00) animated meme video for testing."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    w, h = 640, 360
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(output_path, fourcc, fps, (w, h))

    total_frames = int(duration * fps)
    for i in range(total_frames):
        # Pure pure chroma-key green canvas (BGR: 0, 255, 0)
        frame = np.zeros((h, w, 3), dtype=np.uint8)
        frame[:, :] = (0, 255, 0)

        # Draw an animated expanding red impact skull / hitmarker
        progress = i / float(total_frames)
        radius = int(20 + 40 * np.sin(progress * np.pi))
        center = (w // 2, h // 2)

        # White cross
        cv2.line(frame, (center[0] - radius, center[1] - radius), (center[0] + radius, center[1] + radius), (255, 255, 255), 4)
        cv2.line(frame, (center[0] - radius, center[1] + radius), (center[0] + radius, center[1] - radius), (255, 255, 255), 4)
        # Red center ring
        cv2.circle(frame, center, radius // 2, (0, 0, 255), -1)
        out.write(frame)

    out.release()


def _generate_sample_cutaway_clip(output_path: str, duration: float = 2.5, fps: int = 30):
    """Generates a synthetic dramatic cutaway card (e.g. TO BE CONTINUED / WASTED)."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    w, h = 1080, 1920
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(output_path, fourcc, fps, (w, h))

    total_frames = int(duration * fps)
    for i in range(total_frames):
        # Sepia / dramatic dark background
        frame = np.zeros((h, w, 3), dtype=np.uint8)
        frame[:, :] = (20, 20, 25)

        # Cinematic bars & text
        text = "TO BE CONTINUED ->" if i % 10 < 7 else "TO BE CONTINUED"
        cv2.putText(frame, text, (w // 2 - 280, h // 2), cv2.FONT_HERSHEY_DUPLEX, 1.6, (0, 215, 255), 3, cv2.LINE_AA)
        cv2.putText(frame, "MEME CUTAWAY", (w // 2 - 160, h // 2 + 70), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (200, 200, 200), 2, cv2.LINE_AA)
        out.write(frame)

    out.release()


def get_available_memes(trigger_type: str, injection_type: str) -> List[str]:
    """
    Discovers all compatible meme files for a given trigger and injection mode.
    Checks trigger subfolder first, then falls back to general category folder recursively.
    """
    ensure_meme_asset_structure()

    extensions = {
        "cutaway": ("*.mp4", "*.mov", "*.mkv", "*.webm"),
        "overlay": ("*.mp4", "*.mov", "*.webm"),
        "audio": ("*.mp3", "*.wav", "*.ogg", "*.aac", "*.flac"),
    }

    allowed_exts = extensions.get(injection_type, ("*.*",))
    trigger_map = TRIGGER_ASSET_MAP.get(trigger_type, TRIGGER_ASSET_MAP["general"])
    primary_dir = trigger_map.get(injection_type, str(DEFAULT_MEMES_DIR / injection_type))
    fallback_dir = str(DEFAULT_MEMES_DIR / injection_type)

    found_files = []
    # 1. Search trigger-specific folder
    if os.path.isdir(primary_dir):
        for ext in allowed_exts:
            found_files.extend(glob.glob(os.path.join(primary_dir, ext)))
            found_files.extend(glob.glob(os.path.join(primary_dir, "**", ext), recursive=True))

    # 2. If empty, search fallback general folder recursively
    if not found_files and os.path.isdir(fallback_dir):
        for ext in allowed_exts:
            found_files.extend(glob.glob(os.path.join(fallback_dir, ext)))
            found_files.extend(glob.glob(os.path.join(fallback_dir, "**", ext), recursive=True))

    return sorted(list(set(found_files)))


def select_meme(trigger_type: str, injection_type: str) -> Optional[str]:
    """Randomly selects a meme asset matching the trigger and injection type."""
    candidates = get_available_memes(trigger_type, injection_type)
    if not candidates:
        return None
    return random.choice(candidates)


# ==============================================================================
# 2. INJECTION METHODS
# ==============================================================================

def inject_cutaway_moviepy(
    video_path: str,
    meme_path: str,
    timestamp: float,
    output_path: str
) -> str:
    """
    Cutaway Insertion via MoviePy:
    Slices the main video at timestamp, inserts the cutaway meme video,
    and concatenates them into a unified sequence.
    """
    if not os.path.isfile(video_path):
        raise FileNotFoundError(f"Main video not found: {video_path}")
    if not os.path.isfile(meme_path):
        raise FileNotFoundError(f"Meme cutaway video not found: {meme_path}")

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    print(f"[*] [MoviePy Cutaway] Slicing '{Path(video_path).name}' at t={timestamp:.2f}s with '{Path(meme_path).name}'...")

    main_clip = None
    meme_clip = None
    final_clip = None

    try:
        main_clip = VideoFileClip(video_path)
        main_duration = main_clip.duration

        # Clamp timestamp within valid bounds
        split_t = max(0.0, min(timestamp, main_duration - 0.05))

        # MoviePy 2.x subclipped API
        clip_before = main_clip.subclipped(0, split_t)
        clip_after = main_clip.subclipped(split_t, main_duration)

        # Load meme cutaway and match resolution to main clip
        meme_clip = VideoFileClip(meme_path)
        if (meme_clip.w, meme_clip.h) != (main_clip.w, main_clip.h):
            meme_clip = meme_clip.resized(new_size=(main_clip.w, main_clip.h))

        # Concatenate: [Before, Meme, After]
        final_clip = concatenate_videoclips([clip_before, meme_clip, clip_after], method="compose")

        final_clip.write_videofile(
            output_path,
            codec="libx264",
            audio_codec="aac",
            preset="fast",
            logger=None
        )
    finally:
        # Guarantee closure of file handles on Windows
        for c in [final_clip, meme_clip, main_clip]:
            if c is not None:
                try:
                    c.close()
                except Exception:
                    pass

    print(f"[+] [MoviePy Cutaway] Successfully rendered: {output_path}")
    return output_path


def inject_greenscreen_overlay_ffmpeg(
    video_path: str,
    meme_path: str,
    timestamp: float,
    output_path: str,
    chromakey_color: str = "0x00FF00",
    similarity: float = 0.3,
    blend: float = 0.1,
    scale_factor: float = 1.0,
    overlay_position: str = "(W-w)/2:(H-h)/2",
    ffmpeg_binary: str = "ffmpeg"
) -> str:
    """
    Green Screen Overlay via FFmpeg subprocess:
    Strips green background using chromakey filter and overlays the meme
    onto the gameplay footage at the specified timestamp.
    Preserves natural game sounds; if the meme includes audio, it is mixed in.
    """
    if not os.path.isfile(video_path):
        raise FileNotFoundError(f"Main video not found: {video_path}")
    if not os.path.isfile(meme_path):
        raise FileNotFoundError(f"Meme overlay video not found: {meme_path}")

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    print(f"[*] [FFmpeg Overlay] Chromakeying '{Path(meme_path).name}' over '{Path(video_path).name}' at t={timestamp:.2f}s...")

    # Check if meme file contains an audio stream
    has_audio_cmd = [
        "ffprobe", "-v", "error",
        "-select_streams", "a",
        "-show_entries", "stream=codec_type",
        "-of", "default=noprint_wrappers=1:nokey=1",
        meme_path
    ]
    probe_res = subprocess.run(has_audio_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    meme_has_audio = bool(probe_res.stdout.strip())

    delay_ms = int(max(0.0, timestamp) * 1000)

    # Video filter graph:
    # 1. Chromakey the green screen meme
    # 2. Scale if requested
    # 3. Offset presentation timestamp (PTS) so it appears at 'timestamp'
    # 4. Overlay onto gameplay [0:v]
    filter_video = (
        f"[1:v]chromakey={chromakey_color}:{similarity}:{blend},"
        f"scale=iw*{scale_factor}:ih*{scale_factor},"
        f"setpts=PTS-STARTPTS+{timestamp:.2f}/TB[fg];"
        f"[0:v][fg]overlay={overlay_position}:eof_action=pass[v_out]"
    )

    if meme_has_audio:
        # Mix meme audio at timestamp with natural game audio (NO extra music/radio)
        filter_complex = (
            f"{filter_video};"
            f"[1:a]adelay={delay_ms}|{delay_ms},volume=1.4[meme_a];"
            f"[0:a][meme_a]amix=inputs=2:normalize=0,alimiter=limit=0.98:level=true[a_out]"
        )
        maps = ["-map", "[v_out]", "-map", "[a_out]"]
    else:
        # Preserve natural game audio directly without alteration
        filter_complex = filter_video
        maps = ["-map", "[v_out]", "-map", "0:a"]

    cmd = [
        ffmpeg_binary, "-y",
        "-i", video_path,
        "-i", meme_path,
        "-filter_complex", filter_complex,
        *maps,
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "18",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "192k",
        "-movflags", "+faststart",
        output_path
    ]

    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if res.returncode != 0:
        err = res.stderr[-800:] if res.stderr else "Unknown error"
        raise RuntimeError(f"FFmpeg green screen injection failed (code {res.returncode}):\n{err}")

    print(f"[+] [FFmpeg Overlay] Successfully rendered: {output_path}")
    return output_path


def inject_audio_sfx_ffmpeg(
    video_path: str,
    sfx_path: str,
    timestamp: float,
    output_path: str,
    sfx_volume: float = 1.6,
    ffmpeg_binary: str = "ffmpeg"
) -> str:
    """
    Audio SFX Injection via FFmpeg:
    Mixes the audio meme into the main video's audio track at the exact event
    timestamp without re-encoding or altering the video frames (-c:v copy).
    Preserves 100% natural game audio; never injects background music or radio chatter.
    """
    if not os.path.isfile(video_path):
        raise FileNotFoundError(f"Main video not found: {video_path}")
    if not os.path.isfile(sfx_path):
        raise FileNotFoundError(f"SFX audio not found: {sfx_path}")

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    print(f"[*] [Audio SFX] Mixing '{Path(sfx_path).name}' into '{Path(video_path).name}' at t={timestamp:.2f}s...")

    delay_ms = int(max(0.0, timestamp) * 1000)

    # Delay SFX to trigger point, amix with natural game audio, apply broadcast limiter
    filter_complex = (
        f"[1:a]adelay={delay_ms}|{delay_ms},volume={sfx_volume}[sfx];"
        f"[0:a][sfx]amix=inputs=2:normalize=0,alimiter=limit=0.98:level=true[a_out]"
    )

    cmd = [
        ffmpeg_binary, "-y",
        "-i", video_path,
        "-i", sfx_path,
        "-filter_complex", filter_complex,
        "-map", "0:v",              # Preserve exact original video frames
        "-map", "[a_out]",          # Mixed audio
        "-c:v", "copy",             # Lossless zero re-encode video pass-through
        "-c:a", "aac",
        "-b:a", "192k",
        "-movflags", "+faststart",
        output_path
    ]

    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if res.returncode != 0:
        err = res.stderr[-800:] if res.stderr else "Unknown error"
        raise RuntimeError(f"FFmpeg Audio SFX injection failed (code {res.returncode}):\n{err}")

    print(f"[+] [Audio SFX] Successfully rendered: {output_path}")
    return output_path


def inject_audio_sfx_moviepy(
    video_path: str,
    sfx_path: str,
    timestamp: float,
    output_path: str,
    sfx_volume: float = 1.6
) -> str:
    """
    Audio SFX Injection via MoviePy:
    Alternative implementation using MoviePy CompositeAudioClip.
    Preserves natural game audio track and overlays SFX at timestamp.
    """
    if not os.path.isfile(video_path):
        raise FileNotFoundError(f"Main video not found: {video_path}")
    if not os.path.isfile(sfx_path):
        raise FileNotFoundError(f"SFX audio not found: {sfx_path}")

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    print(f"[*] [MoviePy Audio SFX] Layering '{Path(sfx_path).name}' at t={timestamp:.2f}s...")

    video = None
    sfx = None
    comp_audio = None

    try:
        video = VideoFileClip(video_path)
        sfx = AudioFileClip(sfx_path)

        # Apply volume and timing in MoviePy 2.x
        if hasattr(sfx, "with_volume_scaled"):
            sfx = sfx.with_volume_scaled(sfx_volume)
        elif hasattr(sfx, "volumex"):
            sfx = sfx.volumex(sfx_volume)

        sfx_timed = sfx.with_start(timestamp)
        comp_audio = CompositeAudioClip([video.audio, sfx_timed])

        final_video = video.with_audio(comp_audio)
        final_video.write_videofile(
            output_path,
            codec="libx264",
            audio_codec="aac",
            preset="fast",
            logger=None
        )
    finally:
        for c in [comp_audio, sfx, video]:
            if c is not None:
                try:
                    c.close()
                except Exception:
                    pass

    return output_path


# ==============================================================================
# 3. MAIN ORCHESTRATION FUNCTION
# ==============================================================================

def inject_meme(
    video_path: str,
    timestamp: float,
    trigger_type: str,
    injection_type: Optional[str] = None,
    output_path: Optional[str] = None,
    meme_file: Optional[str] = None,
    **kwargs
) -> str:
    """
    Main Orchestrator for Meme Injection:
    Accepts a video file, timestamp, and trigger type.
    Selects a meme from the asset bank and injects it using Cutaway (MoviePy),
    Green Screen Overlay (FFmpeg), or Audio SFX Only (FFmpeg/MoviePy).

    Args:
        video_path: Path to target gameplay video.
        timestamp: Event timestamp in seconds where the meme should occur.
        trigger_type: Event trigger (e.g. 'high_audio_peak', 'kill_confirmed', 'takedown', 'headshot').
        injection_type: 'cutaway', 'overlay', or 'audio' (auto-selected if None).
        output_path: Output video path. If None, auto-generated in output/memes/.
        meme_file: Optional explicit path to a meme file.
        **kwargs: Extra parameters passed to the specific injection engine
                  (e.g., chromakey_color, similarity, sfx_volume, use_moviepy).

    Returns:
        Path to the output video with injected meme.
    """
    video_path = os.path.abspath(video_path)
    if not os.path.isfile(video_path):
        raise FileNotFoundError(f"Input video does not exist: {video_path}")

    ensure_meme_asset_structure()

    # 1. Determine injection type if not specified
    if injection_type is None:
        injection_type = random.choice(["overlay", "audio", "cutaway"])

    injection_type = injection_type.lower()
    if injection_type not in ("cutaway", "overlay", "audio"):
        raise ValueError(f"Invalid injection_type: '{injection_type}'. Choose from 'cutaway', 'overlay', 'audio'.")

    # 2. Select meme asset
    if meme_file is None:
        meme_file = select_meme(trigger_type, injection_type)
        if not meme_file:
            raise FileNotFoundError(f"No meme assets found for trigger '{trigger_type}' and type '{injection_type}'.")

    # 3. Formulate output path
    if output_path is None:
        out_dir = BASE_DIR / "output" / "memes"
        out_dir.mkdir(parents=True, exist_ok=True)
        stem = Path(video_path).stem
        meme_stem = Path(meme_file).stem
        output_path = str(out_dir / f"{stem}_{injection_type}_{meme_stem}_t{int(timestamp)}s.mp4")

    print("\n" + "=" * 64)
    print(f"  VIDEOAI MEME INJECTOR")
    print(f"  Target Video   : {Path(video_path).name}")
    print(f"  Timestamp      : {timestamp:.2f}s")
    print(f"  Trigger Type   : {trigger_type}")
    print(f"  Injection Mode : {injection_type.upper()}")
    print(f"  Meme Asset     : {Path(meme_file).name}")
    print("=" * 64)

    # 4. Dispatch to appropriate injection method
    if injection_type == "cutaway":
        return inject_cutaway_moviepy(
            video_path=video_path,
            meme_path=meme_file,
            timestamp=timestamp,
            output_path=output_path
        )
    elif injection_type == "overlay":
        return inject_greenscreen_overlay_ffmpeg(
            video_path=video_path,
            meme_path=meme_file,
            timestamp=timestamp,
            output_path=output_path,
            chromakey_color=kwargs.get("chromakey_color", "0x00FF00"),
            similarity=kwargs.get("similarity", 0.3),
            blend=kwargs.get("blend", 0.1),
            scale_factor=kwargs.get("scale_factor", 1.0),
            overlay_position=kwargs.get("overlay_position", "(W-w)/2:(H-h)/2")
        )
    elif injection_type == "audio":
        if kwargs.get("use_moviepy", False):
            return inject_audio_sfx_moviepy(
                video_path=video_path,
                sfx_path=meme_file,
                timestamp=timestamp,
                output_path=output_path,
                sfx_volume=kwargs.get("sfx_volume", 1.6)
            )
        else:
            return inject_audio_sfx_ffmpeg(
                video_path=video_path,
                sfx_path=meme_file,
                timestamp=timestamp,
                output_path=output_path,
                sfx_volume=kwargs.get("sfx_volume", 1.6)
            )

    return output_path


def main():
    parser = argparse.ArgumentParser(description="VideoAI Meme Injector")
    parser.add_argument("video", help="Path to input video")
    parser.add_argument("--timestamp", "-t", type=float, required=True, help="Timestamp in seconds to inject the meme")
    parser.add_argument("--trigger", "-g", default="high_audio_peak", help="Trigger type (high_audio_peak, kill_confirmed, takedown, headshot)")
    parser.add_argument("--type", "-m", choices=["cutaway", "overlay", "audio"], default=None, help="Injection mode (cutaway, overlay, audio)")
    parser.add_argument("--meme", default=None, help="Explicit meme file path (optional)")
    parser.add_argument("--output", "-o", default=None, help="Output file path (optional)")
    parser.add_argument("--chromakey", default="0x00FF00", help="Chroma key color hex (default: 0x00FF00)")
    parser.add_argument("--volume", type=float, default=1.6, help="SFX volume multiplier (default: 1.6)")

    args = parser.parse_args()

    result = inject_meme(
        video_path=args.video,
        timestamp=args.timestamp,
        trigger_type=args.trigger,
        injection_type=args.type,
        output_path=args.output,
        meme_file=args.meme,
        chromakey_color=args.chromakey,
        sfx_volume=args.volume
    )

    print(f"\n[+] Meme Injection Completed: {result}")


if __name__ == "__main__":
    main()
