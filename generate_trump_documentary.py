import os
import subprocess
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

from trump_script_data import DOCUMENTARY_SCRIPT
from voice_synthesizer import synthesize_narration, get_audio_duration
from youtube_broll import fetch_youtube_broll

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = PROJECT_ROOT / "output" / "Trump_Documentary"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

FINAL_OUTPUT = OUTPUT_DIR / "Trump_Pledge_Analysis.mp4"
MUSIC_TRACK = PROJECT_ROOT / "assets" / "epidemic_sound" / "Wrath.mp3"

FFMPEG = "ffmpeg"

import textwrap

def create_cnn_style_overlay(output_dir, headline, ticker, chapter_idx):
    # 1920x1080 transparent image
    im = Image.new("RGBA", (1920, 1080), (0, 0, 0, 0))
    draw = ImageDraw.Draw(im)
    
    # Colors
    cnn_red = (204, 0, 0, 255)
    white = (255, 255, 255, 255)
    black = (10, 10, 10, 255)
    
    try:
        f_headline = ImageFont.truetype("C:/Windows/Fonts/impact.ttf", 65)
        f_ticker = ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", 35)
        f_live = ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", 40)
    except:
        f_headline = ImageFont.load_default()
        f_ticker = ImageFont.load_default()
        f_live = ImageFont.load_default()
        
    # --- LIVE BADGE (Top Right) ---
    draw.rectangle([(1700, 50), (1850, 110)], fill=cnn_red)
    draw.text((1725, 60), "LIVE", font=f_live, fill=white)
    
    # --- BOTTOM TICKER BAR ---
    draw.rectangle([(0, 980), (1920, 1040)], fill=black)
    wrapped_ticker = textwrap.fill(ticker.upper(), width=100)
    ticker_lines = wrapped_ticker.split('\n')
    draw.text((50, 990), ticker_lines[0], font=f_ticker, fill=(255, 215, 0, 255))
    
    # --- HEADLINE BOX (Above Ticker) ---
    wrapped_headline = textwrap.fill(headline.upper(), width=40)
    head_lines = wrapped_headline.split('\n')
    
    box_height = 40 + (len(head_lines) * 75)
    box_top = 960 - box_height
    
    draw.rectangle([(100, box_top), (1700, 960)], fill=white)
    draw.rectangle([(100, box_top), (120, 960)], fill=cnn_red)
    
    y_offset = box_top + 15
    for line in head_lines:
        draw.text((140, y_offset), line, font=f_headline, fill=black)
        y_offset += 75
        
    overlay_path = output_dir / f"overlay_ch_{chapter_idx}.png"
    im.save(overlay_path)
    return overlay_path

def build_documentary():
    print(f"--- Starting Render: {DOCUMENTARY_SCRIPT['title']} ---")
    
    shots = []
    audios = []
    
    current_time_offset = 0.0
    
    # Render Chapters
    for idx, chapter in enumerate(DOCUMENTARY_SCRIPT["chapters"]):
        print(f"\nProcessing Chapter {idx+1}: {chapter['title']}")
        
        # 1. Synthesize Audio
        audio_file = f"trump_ch_{idx}.mp3"
        audio_path, dur, _ = synthesize_narration(
            text=chapter['narration'],
            output_filename=audio_file,
            provider="openai",
            voice="echo"
        )
        audios.append({"path": audio_path, "type": "voice", "delay": current_time_offset})
        
        # 2. Fetch B-roll from YouTube
        print(f"Fetching B-roll for: '{chapter['broll_query']}'")
        shot_dur = dur + 1.0 # padding
        broll_clip_path = fetch_youtube_broll(
            query=chapter['broll_query'], 
            target_duration=shot_dur, 
            license_policy="any" # User stated: under fair use / reaction
        )
        
        # 3. Create CNN Overlay
        overlay_img = create_cnn_style_overlay(OUTPUT_DIR, chapter['headline'], chapter['ticker'], idx)
        
        shot_out = OUTPUT_DIR / f"shot_ch_{idx:02d}.mp4"
        
        if broll_clip_path and os.path.exists(broll_clip_path):
            print(f"Applying CNN graphics to {broll_clip_path}...")
            # Scale B-roll to 1920x1080 and apply overlay
            cmd = [
                FFMPEG, "-y",
                "-i", str(broll_clip_path),
                "-i", str(overlay_img),
                "-filter_complex", "[0:v]scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1[vbg];[vbg][1:v]overlay=0:0[vout]",
                "-map", "[vout]",
                "-t", str(shot_dur),
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
                "-an",
                str(shot_out)
            ]
            subprocess.run(cmd, check=True)
            shots.append(shot_out)
        else:
            print(f"Failed to fetch B-roll for '{chapter['broll_query']}'. Using black background fallback.")
            cmd = [
                FFMPEG, "-y",
                "-f", "lavfi", "-i", f"color=c=black:s=1920x1080:d={shot_dur}",
                "-i", str(overlay_img),
                "-filter_complex", "[0:v][1:v]overlay=0:0[vout]",
                "-map", "[vout]",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
                "-an",
                str(shot_out)
            ]
            subprocess.run(cmd, check=True)
            shots.append(shot_out)
            
        current_time_offset += shot_dur

    # Concatenate Video
    concat_list = OUTPUT_DIR / "shots_concat.txt"
    with open(concat_list, "w", encoding="utf-8") as f:
        for sf in shots:
            f.write(f"file '{sf.resolve().as_posix()}'\n")

    concatenated_raw = OUTPUT_DIR / "raw_video_track.mp4"
    cmd = [
        FFMPEG, "-y",
        "-f", "concat", "-safe", "0",
        "-i", str(concat_list),
        "-c", "copy",
        str(concatenated_raw)
    ]
    subprocess.run(cmd, check=True)
    
    # Audio Mixing
    filter_complex = ""
    inputs = [f"-i", str(concatenated_raw)]
    
    current_input_idx = 1
    
    has_music = MUSIC_TRACK.exists()
    mix_components = []
    
    if has_music:
        inputs.extend(["-i", str(MUSIC_TRACK)])
        music_idx = current_input_idx
        current_input_idx += 1
        # Duck music slightly
        filter_complex += f"[{music_idx}:a]volume=0.15[music_ducked];"
        mix_components.append("[music_ducked]")
    
    for idx, audio in enumerate(audios):
        inputs.extend(["-i", audio["path"]])
        delay_ms = int(audio["delay"] * 1000)
        filter_complex += f"[{current_input_idx}:a]adelay={delay_ms}|{delay_ms},volume=1.5[a_{idx}];"
        mix_components.append(f"[a_{idx}]")
        current_input_idx += 1
                
    mix_count = len(mix_components)
    mix_str = "".join(mix_components)
    filter_complex += f"{mix_str}amix=inputs={mix_count}:duration=first:dropout_transition=2,loudnorm=I=-14:TP=-1.5:LRA=8[afinal]"

    print("\nRendering final documentary...")
    render_cmd = [
        FFMPEG, "-y"
    ] + inputs + [
        "-filter_complex", filter_complex,
        "-map", "0:v",
        "-map", "[afinal]",
        "-c:v", "h264_nvenc", "-preset", "p5", "-cq", "20",
        "-c:a", "aac", "-b:a", "320k",
        str(FINAL_OUTPUT)
    ]
    
    try:
        subprocess.run(render_cmd, check=True)
    except subprocess.CalledProcessError:
        print("NVENC failed, falling back to libx264...")
        render_cmd[render_cmd.index("h264_nvenc")] = "libx264"
        render_cmd[render_cmd.index("-cq")] = "-crf"
        subprocess.run(render_cmd, check=True)

    print(f"\nSUCCESS! Documentary rendered to {FINAL_OUTPUT}")

if __name__ == "__main__":
    build_documentary()
