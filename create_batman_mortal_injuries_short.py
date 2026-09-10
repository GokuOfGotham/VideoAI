"""
Batman Knightfall: The Mortal Injuries Before Bane Short Video Generator
Topic: How Batman had mortal injuries way before Bane broke his back.
Narration: OpenAI TTS (onyx, tts-1-hd)
Source Video: M:/Videos/Gaming/Batman Knightfall Part 1 Batman VS Bane Final Epic Fight Scene!.mp4
Music: Epidemic Sound Wrath.mp3
SFX: assets/epidemic_sound/sfx/
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).resolve().parent
SOURCE_VIDEO = "M:/Videos/Gaming/Batman Knightfall Part 1 Batman VS Bane Final Epic Fight Scene!.mp4"
OUTPUT_DIR = PROJECT_ROOT / "output" / "Batman_Knightfall_Mortal_Injuries"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

FINAL_OUTPUT = OUTPUT_DIR / "Batman_Had_Mortal_Injuries_Before_Bane_Short.mp4"
AUDIO_VOICE = PROJECT_ROOT / "assets" / "batman_knightfall" / "narration_onyx.mp3"
TIMESTAMPS_JSON = PROJECT_ROOT / "assets" / "batman_knightfall" / "word_timestamps.json"
SUBTITLES_ASS = OUTPUT_DIR / "subtitles.ass"
MUSIC_TRACK = PROJECT_ROOT / "assets" / "epidemic_sound" / "Wrath.mp3"
SFX_DIR = PROJECT_ROOT / "assets" / "epidemic_sound" / "sfx"
SFX_BONE = SFX_DIR / "Gore__Bone__Crush__Crunch.mp3"

FFMPEG = "ffmpeg"
FFPROBE = "ffprobe"

def get_duration(file_path):
    cmd = [FFPROBE, "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(file_path)]
    res = subprocess.check_output(cmd).decode().strip()
    return float(res)

def format_ass_time(seconds: float) -> str:
    cs = int(round(seconds * 100))
    h = cs // 360000
    m = (cs % 360000) // 6000
    s = (cs % 6000) // 100
    c = cs % 100
    return f"{h:01d}:{m:02d}:{s:02d}.{c:02d}"

def build_ass_subtitles(words_file, output_ass):
    with open(words_file, "r", encoding="utf-8") as f:
        words = json.load(f)

    header = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Impact,70,&H00FFFFFF&,&H00000000&,&H00000000&,&H80000000,-1,0,0,0,100,100,0,0,1,5,2,2,50,50,450,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = []
    chunks = []
    curr = []
    for w in words:
        curr.append(w)
        if len(curr) >= 2:
            chunks.append(curr)
            curr = []
    if curr:
        chunks.append(curr)

    for chunk in chunks:
        c_start = float(chunk[0]["start"])
        c_end = float(chunk[-1]["end"])
        for i, target in enumerate(chunk):
            w_start = format_ass_time(target["start"])
            w_end = format_ass_time(chunk[i+1]["start"] if i+1 < len(chunk) else c_end)
            text_parts = []
            for j, w in enumerate(chunk):
                w_str = w["word"].strip().upper()
                if j == i:
                    text_parts.append("{\\c&H0000E5FF&\\b1}" + w_str + "{\\c&H00FFFFFF&\\b0}")
                else:
                    text_parts.append(w_str)
            line = f"Dialogue: 0,{w_start},{w_end},Default,,0,0,0,,{' '.join(text_parts)}"
            events.append(line)

    with open(output_ass, "w", encoding="utf-8-sig") as f:
        f.write(header + "\n".join(events) + "\n")
    print(f"Generated {len(events)} ASS subtitle events -> {output_ass}")

def create_branding_overlays(output_dir):
    im = Image.new("RGBA", (1080, 1920), (0, 0, 0, 0))
    draw = ImageDraw.Draw(im)

    for y in range(450):
        alpha = int(220 * (1 - y / 450.0))
        draw.line([(0, y), (1080, y)], fill=(0, 0, 0, alpha))

    gold = (255, 204, 0, 255)
    cyan = (0, 229, 255, 255)
    white = (255, 255, 255, 255)
    dark_bg = (10, 12, 16, 240)

    draw.rounded_rectangle([(140, 170), (940, 245)], radius=12, fill=dark_bg, outline=gold, width=3)

    try:
        f_badge = ImageFont.truetype("C:/Windows/Fonts/impact.ttf", 36)
        f_main = ImageFont.truetype("C:/Windows/Fonts/impact.ttf", 66)
        f_sub = ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", 30)
    except:
        f_badge = ImageFont.load_default()
        f_main = ImageFont.load_default()
        f_sub = ImageFont.load_default()

    draw.text((540, 207), "KNIGHTFALL: THE UNTOLD TRUTH", font=f_badge, fill=gold, anchor="mm")
    draw.text((540, 310), "BATMAN WAS ALREADY DYING", font=f_main, fill=white, anchor="mm")
    draw.text((540, 380), "MORTAL INJURIES BEFORE BANE BROKE HIM", font=f_sub, fill=cyan, anchor="mm")

    draw.line([(60, 645), (1020, 645)], fill=(255, 204, 0, 220), width=3)
    draw.line([(60, 1255), (1020, 1255)], fill=(255, 204, 0, 220), width=3)

    overlay_path = output_dir / "header_overlay.png"
    im.save(overlay_path)
    print(f"Header overlay generated -> {overlay_path}")
    return overlay_path

def render_final_video():
    total_duration = get_duration(AUDIO_VOICE)
    print(f"Voiceover duration: {total_duration:.2f}s")

    build_ass_subtitles(TIMESTAMPS_JSON, SUBTITLES_ASS)
    overlay_img = create_branding_overlays(OUTPUT_DIR)

    shots = [
        (205.0, 5.0),
        (143.0, 5.5),
        (0.0, 5.5),
        (62.0, 6.0),
        (51.0, 5.5),
        (160.0, 5.5),
        (21.0, 5.5),
        (103.0, 5.5),
        (185.0, 5.5),
        (205.0, 6.20),
    ]

    shot_files = []
    print("\nExtracting and formatting individual video shots...")
    for idx, (start_sec, dur) in enumerate(shots):
        shot_out = OUTPUT_DIR / f"shot_{idx:02d}.mp4"
        cmd = [
            FFMPEG, "-y",
            "-ss", str(start_sec),
            "-t", str(dur),
            "-i", SOURCE_VIDEO,
            "-vf", "fps=30,setsar=1",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
            "-an",
            str(shot_out)
        ]
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        shot_files.append(shot_out)
        print(f"  Processed shot {idx+1}/{len(shots)} ({dur}s)")

    concat_list = OUTPUT_DIR / "shots_concat.txt"
    with open(concat_list, "w", encoding="utf-8") as f:
        for sf in shot_files:
            f.write(f"file '{sf.resolve().as_posix()}'\n")

    concatenated_raw = OUTPUT_DIR / "raw_video_track.mp4"
    cmd = [
        FFMPEG, "-y",
        "-f", "concat", "-safe", "0",
        "-i", str(concat_list),
        "-c", "copy",
        str(concatenated_raw)
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    print("Concatenated video shots successfully.")

    escaped_ass = str(SUBTITLES_ASS).replace("\\", "/").replace(":", "\\:")

    filter_complex = (
        "[0:v]split=2[raw_bg][raw_fg];"
        "[raw_bg]scale=270:480:force_original_aspect_ratio=increase,crop=270:480,boxblur=15:2,"
        "scale=1080:1920,eq=brightness=-0.22:saturation=0.6[bg];"
        "[raw_fg]scale=1080:608:force_original_aspect_ratio=decrease,setsar=1,"
        "eq=contrast=1.15:saturation=1.12:gamma=1.05[fg];"
        "[bg][fg]overlay=0:647[framed];"
        "[framed][1:v]overlay=0:0[with_hdr];"
        f"[with_hdr]ass='{escaped_ass}'[vfinal];"
        "[2:a]aresample=48000,loudnorm=I=-15:TP=-1.5:LRA=7[voice];"
        "[3:a]aresample=48000,volume=0.22,afade=t=in:d=1,afade=t=out:st=53:d=2.7[music];"
        "[4:a]adelay=50500|50500,volume=1.4[sfx_bone];"
        "[voice][music][sfx_bone]amix=inputs=3:duration=first:dropout_transition=2,loudnorm=I=-14:TP=-1.5:LRA=8[afinal]"
    )

    print("\nRendering final master vertical video with NVENC/GPU acceleration...")
    render_cmd = [
        FFMPEG, "-y",
        "-i", str(concatenated_raw),
        "-i", str(overlay_img),
        "-i", str(AUDIO_VOICE),
        "-i", str(MUSIC_TRACK),
        "-i", str(SFX_BONE),
        "-filter_complex", filter_complex,
        "-map", "[vfinal]",
        "-map", "[afinal]",
        "-t", str(total_duration),
        "-c:v", "h264_nvenc", "-preset", "p5", "-cq", "20", "-b:v", "0",
        "-c:a", "aac", "-b:a", "320k", "-ar", "48000",
        "-movflags", "+faststart",
        str(FINAL_OUTPUT)
    ]

    try:
        subprocess.run(render_cmd, check=True)
    except subprocess.CalledProcessError:
        print("NVENC failed or unavailable, falling back to libx264...")
        render_cmd[render_cmd.index("h264_nvenc")] = "libx264"
        render_cmd[render_cmd.index("-cq")] = "-crf"
        subprocess.run(render_cmd, check=True)

    print(f"\nSUCCESS! Video rendered to:\n{FINAL_OUTPUT}")

    for t_sec in [3.0, 15.0, 35.0, 52.0]:
        prev_img = OUTPUT_DIR / f"Preview_{int(t_sec):02d}s.jpg"
        cmd = [FFMPEG, "-y", "-ss", str(t_sec), "-i", str(FINAL_OUTPUT), "-vframes", "1", "-q:v", "2", str(prev_img)]
        subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    print("Preview images generated.")

if __name__ == "__main__":
    render_final_video()
