"""
Meme FX Engine for VideoAI.

Implements authentic, funny, high-production viral meme effects:
1. GTA V "WASTED" Death/Knockout Sequence (Freeze, desaturate, WASTED banner, wasted.mp3).
2. JoJo "To Be Continued" Cliffhanger (Freeze, sepia grade, iconic TBC arrow, Roundabout bassline).
3. Viral Video Cutaway (e.g., Watch Yo Tone, Sigma Cat, Whoops Fail Scream).
4. Meme Popup Sticker & Sound (e.g., Phil Swift "Now That's A Lot of Damage", Mocking SpongeBob, Minecraft OOF, Bruh).
"""

import math
import os
import subprocess
import time
from pathlib import Path
from typing import Optional

BASE_DIR = Path(__file__).resolve().parent
MEMES_DIR = BASE_DIR / "assets" / "memes"


def get_video_duration(video_path: str) -> float:
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        video_path
    ]
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        return float(res.stdout.strip())
    except Exception:
        return 60.0


def apply_gta_wasted_effect(
    video_path: str,
    timestamp: float,
    output_path: str,
    wasted_duration: float = 2.4
) -> str:
    """
    Applies the authentic GTA V Wasted effect:
    - At timestamp: transitions screen to high-contrast grayscale.
    - Centered 'WASTED' graphic appears.
    - Authentic GTA V wasted audio hit.
    """
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    wasted_png = str(MEMES_DIR / "images" / "wasted.png")
    wasted_mp3 = str(MEMES_DIR / "audio" / "wasted.mp3")

    total_dur = get_video_duration(video_path)
    t0 = max(0.0, timestamp)
    t1 = t0 + wasted_duration
    delay_ms = int(t0 * 1000)

    filter_complex = f"""
[0:v]hue=s=0:enable='between(t,{t0:.2f},{t1:.2f})'[v_desat];
[1:v]scale=720:-1[wasted_scaled];
[v_desat][wasted_scaled]overlay=(W-w)/2:(H-h)/2:enable='between(t,{t0:.2f},{t1:.2f})'[v_out];

[2:a]volume=1.8,adelay={delay_ms}|{delay_ms},apad[a_wasted_sfx];
[0:a][a_wasted_sfx]amix=inputs=2:duration=first:dropout_transition=0,alimiter=limit=0.98:level=true:attack=5:release=50[a_out]
"""

    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
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
        "-t", f"{total_dur:.2f}",
        "-movflags", "+faststart",
        output_path
    ]

    print(f"[*] Applying GTA V Wasted effect at t={timestamp:.2f}s...")
    subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return output_path


def apply_to_be_continued_effect(
    video_path: str,
    timestamp: float,
    output_path: str,
    freeze_duration: float = 3.0
) -> str:
    """
    Applies the iconic JoJo 'To Be Continued' freeze-frame:
    - Sepia/amber color grade at timestamp.
    - JoJo 'To Be Continued' arrow overlay on bottom-left.
    - Roundabout bassline groove (to_be_continued.mp3).
    """
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    tbc_png = str(MEMES_DIR / "images" / "to_be_continued.png")
    tbc_mp3 = str(MEMES_DIR / "audio" / "to_be_continued.mp3")

    total_dur = get_video_duration(video_path)
    t0 = max(0.0, timestamp)
    t1 = t0 + freeze_duration
    delay_ms = int(t0 * 1000)

    filter_complex = f"""
[0:v]colorchannelmixer=.393:.769:.189:0:.349:.686:.168:0:.272:.534:.131:0:enable='between(t,{t0:.2f},{t1:.2f})'[v_sepia];
[1:v]scale=560:-1[tbc_scaled];
[v_sepia][tbc_scaled]overlay=40:H-h-80:enable='between(t,{t0:.2f},{t1:.2f})'[v_out];

[2:a]volume=1.8,adelay={delay_ms}|{delay_ms},apad[a_tbc_sfx];
[0:a][a_tbc_sfx]amix=inputs=2:duration=first:dropout_transition=0,alimiter=limit=0.98:level=true:attack=5:release=50[a_out]
"""

    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-i", tbc_png,
        "-i", tbc_mp3,
        "-filter_complex", filter_complex,
        "-map", "[v_out]",
        "-map", "[a_out]",
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "18",
        "-c:a", "aac",
        "-b:a", "256k",
        "-t", f"{total_dur:.2f}",
        "-movflags", "+faststart",
        output_path
    ]

    print(f"[*] Applying JoJo To Be Continued effect at t={timestamp:.2f}s...")
    subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return output_path


def apply_viral_cutaway(
    video_path: str,
    timestamp: float,
    cutaway_video_path: str,
    output_path: str,
    max_cutaway_duration: float = 3.5
) -> str:
    """
    Slices gameplay at timestamp and inserts a viral reaction cutaway
    (e.g., Watch Yo Tone, Sigma Cat, Whoops Fail Scream).
    """
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    t0 = max(0.0, timestamp)

    filter_complex = f"""
[0:v]trim=start=0:end={t0:.2f},setpts=PTS-STARTPTS[v_pre];
[0:a]atrim=start=0:end={t0:.2f},asetpts=PTS-STARTPTS[a_pre];

[1:v]trim=0:{max_cutaway_duration:.2f},setpts=PTS-STARTPTS,scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(1080-iw)/2:(1920-ih)/2:black,setsar=1,fps=30[v_meme];
[1:a]atrim=0:{max_cutaway_duration:.2f},asetpts=PTS-STARTPTS,volume=1.5[a_meme];

[0:v]trim=start={t0:.2f},setpts=PTS-STARTPTS[v_post];
[0:a]atrim=start={t0:.2f},asetpts=PTS-STARTPTS[a_post];

[v_pre][a_pre][v_meme][a_meme][v_post][a_post]concat=n=3:v=1:a=1[v_out][a_out]
"""

    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-i", cutaway_video_path,
        "-filter_complex", filter_complex,
        "-map", "[v_out]",
        "-map", "[a_out]",
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "19",
        "-c:a", "aac",
        "-b:a", "256k",
        "-movflags", "+faststart",
        output_path
    ]

    print(f"[*] Slicing in viral cutaway ({Path(cutaway_video_path).name}) at t={timestamp:.2f}s...")
    subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return output_path


def apply_meme_sticker_popup(
    video_path: str,
    timestamp: float,
    sticker_image_path: str,
    sound_fx_path: str,
    output_path: str,
    duration: float = 2.0,
    sticker_width: int = 480
) -> str:
    """
    Pops up a funny sticker (e.g. Phil Swift, Mocking SpongeBob, Gigachad)
    accompanied by an iconic sound effect (Minecraft OOF, Bruh, Laughing Guy).
    """
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    total_dur = get_video_duration(video_path)
    t0 = max(0.0, timestamp)
    t1 = t0 + duration
    delay_ms = int(t0 * 1000)

    filter_complex = f"""
[1:v]scale={sticker_width}:-1[sticker];
[0:v][sticker]overlay=(W-w)/2:H-h-160:enable='between(t,{t0:.2f},{t1:.2f})'[v_out];

[2:a]volume=1.6,adelay={delay_ms}|{delay_ms},apad[a_sfx];
[0:a][a_sfx]amix=inputs=2:duration=first:dropout_transition=0,alimiter=limit=0.98:level=true:attack=5:release=50[a_out]
"""

    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-i", sticker_image_path,
        "-i", sound_fx_path,
        "-filter_complex", filter_complex,
        "-map", "[v_out]",
        "-map", "[a_out]",
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "18",
        "-c:a", "aac",
        "-b:a", "256k",
        "-t", f"{total_dur:.2f}",
        "-movflags", "+faststart",
        output_path
    ]

    print(f"[*] Applying sticker popup ({Path(sticker_image_path).name} + {Path(sound_fx_path).name}) at t={timestamp:.2f}s...")
    subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return output_path
