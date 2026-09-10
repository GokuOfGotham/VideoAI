"""Strip a clip's original audio and score it with an action track.

Purpose-built for footage that arrives with wind noise, radio chatter, or
engine roar you do not want: the source audio is discarded entirely rather
than ducked, and an Epidemic Sound track is laid underneath.

    python replace_audio_with_music.py "path/to/video.mp4"
    python replace_audio_with_music.py "video.mp4" --search "naval battle drums"
    python replace_audio_with_music.py "video.mp4" --no-upscale

Music retrieved through the Epidemic Sound API is licensed to your account.
Do not redistribute the downloaded audio itself.
"""

import argparse
import os
import subprocess
import sys

from dotenv import load_dotenv

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

load_dotenv()

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from create_military_short import OUTPUT_DIR, fetch_epidemic_action_track  # noqa: E402

FFMPEG = "ffmpeg"
FFPROBE = "ffprobe"

# YouTube normalises to roughly -14 LUFS; mastering to it avoids their
# automatic gain reduction flattening the dynamics on upload.
TARGET_LUFS = -14
FADE_IN = 1.0
FADE_OUT = 2.5


def probe_duration(path: str) -> float:
    out = subprocess.run(
        [FFPROBE, "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", path],
        capture_output=True, text=True, check=True,
    )
    return float(out.stdout.strip())


def probe_resolution(path: str) -> tuple[int, int]:
    out = subprocess.run(
        [FFPROBE, "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "csv=p=0", path],
        capture_output=True, text=True, check=True,
    )
    w, h = out.stdout.strip().split(",")[:2]
    return int(w), int(h)


def build(video_path: str, search_term: str, upscale: bool = True,
          output_path: str | None = None) -> str:
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video not found: {video_path}")

    duration = probe_duration(video_path)
    width, height = probe_resolution(video_path)
    print(f"[*] Source: {os.path.basename(video_path)}")
    print(f"    {width}x{height}, {duration:.1f}s")

    track = fetch_epidemic_action_track(search_term)
    if not track:
        raise RuntimeError("Could not retrieve a music track from Epidemic Sound.")
    music_path = track["local_path"]

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    if output_path is None:
        stem = os.path.splitext(os.path.basename(video_path))[0][:60].strip()
        output_path = os.path.join(OUTPUT_DIR, f"{stem}_SCORED.mp4")

    # Convert to a 1080x1920 vertical frame for Shorts.
    #
    # How depends on the source shape. Padding a landscape clip into 9:16
    # leaves most of the frame black, which reads as lazy on Shorts, so
    # landscape sources are centre-cropped to fill instead. Sources already
    # taller than wide are scaled and padded, since cropping them would cut
    # the subject.
    source_ratio = width / height if height else 0
    target_ratio = 1080 / 1920

    if not upscale or (width, height) == (1080, 1920):
        video_filter = "setsar=1"
    elif source_ratio > target_ratio:
        # Landscape (or wider than 9:16): crop the centre column, then scale.
        video_filter = (
            "crop=w=ih*9/16:h=ih:x=(iw-ih*9/16)/2:y=0,"
            "scale=1080:1920:flags=lanczos,"
            "setsar=1"
        )
        print(f"    Landscape source - centre-cropping to 9:16, then 1080x1920")
    else:
        # Already vertical or square: fit inside the frame, pad the remainder.
        video_filter = (
            "scale=1080:1920:force_original_aspect_ratio=decrease:flags=lanczos,"
            "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=black,"
            "setsar=1"
        )
        print("    Scaling to 1080x1920")

    # Trim the music to the clip, fade both ends, then normalise loudness.
    fade_start = max(0.0, duration - FADE_OUT)
    audio_filter = (
        f"atrim=0:{duration:.3f},"
        f"afade=t=in:st=0:d={FADE_IN},"
        f"afade=t=out:st={fade_start:.3f}:d={FADE_OUT},"
        f"loudnorm=I={TARGET_LUFS}:TP=-1.5:LRA=11"
    )

    cmd = [
        FFMPEG, "-y",
        "-i", video_path,
        "-i", music_path,
        "-filter_complex", f"[0:v]{video_filter}[v];[1:a]{audio_filter}[a]",
        "-map", "[v]",
        "-map", "[a]",          # original audio is never mapped, so it is dropped
        "-c:v", "libx264",
        "-preset", "slow",
        "-crf", "18",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "192k",
        "-ar", "48000",
        "-movflags", "+faststart",
        "-t", f"{duration:.3f}",
        output_path,
    ]

    print(f"[*] Rendering to: {output_path}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed:\n{result.stderr[-1500:]}")

    size_mb = os.path.getsize(output_path) / 1_048_576
    print(f"[+] Done: {size_mb:.1f} MB")
    print(f"    Music: \"{track['title']}\" by {track['artist']} (ISRC: {track['isrc']})")
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("video", help="Path to the source video")
    parser.add_argument("--search", default="epic military action trailer",
                        help="Epidemic Sound search term")
    parser.add_argument("--no-upscale", action="store_true",
                        help="Keep the source resolution instead of scaling to 1080x1920")
    parser.add_argument("-o", "--output", default=None, help="Output path")
    args = parser.parse_args()

    build(args.video, args.search, upscale=not args.no_upscale,
          output_path=args.output)


if __name__ == "__main__":
    main()
