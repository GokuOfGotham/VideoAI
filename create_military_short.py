import os
import glob
import random
import requests
import re
import subprocess
import sys
import time
from pathlib import Path
from dotenv import load_dotenv

# See main.py: Windows pipes default to cp1252, which mangles curly quotes and
# ellipses in generated script text. Affects logs only, but garbled logs hide
# real problems.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

# Load environment variables
load_dotenv()

EPIDEMIC_SOUND_API_KEY = os.getenv('EPIDEMIC_SOUND_API_KEY')
FFMPEG_PATH = 'ffmpeg'
FFPROBE_PATH = 'ffprobe'

# Directories. Override in .env — see .env.example.
PROJECT_ROOT = Path(__file__).resolve().parent
MEDIA_ROOT = os.getenv('MEDIA_ROOT', str(PROJECT_ROOT / 'media'))

MILITARY_VIDEOS_DIR = os.getenv('MILITARY_VIDEOS_DIR', os.path.join(MEDIA_ROOT, 'US Military'))
EPIDEMIC_MUSIC_DIR = os.getenv('EPIDEMIC_MUSIC_DIR', str(PROJECT_ROOT / 'assets' / 'epidemic_sound'))
OUTPUT_DIR = os.getenv('OUTPUT_DIR', str(PROJECT_ROOT / 'output'))

os.makedirs(MILITARY_VIDEOS_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(EPIDEMIC_MUSIC_DIR, exist_ok=True)

# Search queries strictly for Epic Hybrid Orchestral (Hans Zimmer inspired percussion, deep brass, massive impacts, tension-building strings)
EPIDEMIC_ACTION_SEARCH_TERMS = [
    "epic hybrid orchestral trailer",
    "hans zimmer cinematic trailer",
    "deep brass epic orchestral impact",
    "soaring tension building strings"
]

def fetch_epidemic_action_track(search_term: str) -> dict:
    """Connects to Epidemic Sound API and downloads an Epic Hybrid Orchestral score (Hans Zimmer percussion, deep brass & tension strings)."""
    print('\n=======================================================')
    print('   EPIDEMIC SOUND EPIC HYBRID ORCHESTRAL ENGINE (HANS ZIMMER STYLE)')
    print('=======================================================')
    print(f'[*] Searching Epidemic Sound for: "{search_term}"...')
    
    url = "https://www.epidemicsound.com/json/search/tracks/"
    headers = {
        'Authorization': f'Bearer {EPIDEMIC_SOUND_API_KEY}',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    params = {'term': search_term, 'limit': 15}
    
    try:
        res = requests.get(url, headers=headers, params=params, timeout=15)
        res.raise_for_status()
        data = res.json()
        tracks_dict = data.get('entities', {}).get('tracks', {})
        
        candidates = []
        # Exclude electronic techno / synth pop keywords
        forbidden_keywords = ["techno", "synthwave", "cyberpunk", "edm", "pop", "chill"]
        
        for track_id, track in tracks_dict.items():
            stems = track.get('stems', {})
            full_stem = stems.get('full', {})
            mp3_url = full_stem.get('lqMp3Url')
            title = track.get('title', 'Unknown Track')
            isrc = track.get('isrc', 'N/A')
            creatives = track.get('creatives', {}).get('mainArtists', [])
            artist = creatives[0].get('name') if creatives else 'Epidemic Artist'
            
            if mp3_url and not any(kw in title.lower() for kw in forbidden_keywords):
                candidates.append({
                    'id': track_id,
                    'title': title,
                    'artist': artist,
                    'isrc': isrc,
                    'mp3_url': mp3_url
                })
                
        if candidates:
            # Pick from top Epic Hybrid Orchestral matches
            selected_track = random.choice(candidates[:4])
            print(f"[+] Found {len(candidates)} matching Epic Hybrid Orchestral tracks.")
            print(f"[+] SELECTED EPIC HYBRID SCORE: \"{selected_track['title']}\" by {selected_track['artist']} (ISRC: {selected_track['isrc']})")
            
            clean_title = re.sub(r'[^\w\-_]', '_', selected_track['title'])
            download_path = os.path.join(EPIDEMIC_MUSIC_DIR, f"{clean_title}.mp3")
            
            if not os.path.exists(download_path):
                print(f"[*] Downloading stream from Epidemic Sound CDN...")
                audio_res = requests.get(selected_track['mp3_url'], timeout=30)
                with open(download_path, 'wb') as f:
                    f.write(audio_res.content)
                print(f"[+] Audio downloaded ({len(audio_res.content)} bytes) to:\n    {download_path}")
            else:
                print(f"[+] Using cached track:\n    {download_path}")
                
            selected_track['local_path'] = download_path
            print('=======================================================\n')
            return selected_track
    except Exception as err:
        print(f"[!] Epidemic Sound API Search Error: {err}")
        
    print('=======================================================\n')
    return None





def get_video_duration(video_path: str) -> float:
    """Returns duration of video in seconds using ffprobe."""
    cmd = [
        FFPROBE_PATH, "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        video_path
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    try:
        return float(res.stdout.strip())
    except ValueError:
        return 0.0

def build_military_short(video_file: str = None, target_duration: float = 35.0, search_term: str = None, audio_mode: str = "replace"):
    """
    Renders a vertical 9:16 high-action Short from US Military folder
    with Epidemic Sound trailer music (NO text, NO voiceover).
    """

    if not video_file or not os.path.exists(video_file):
        video_files = glob.glob(os.path.join(MILITARY_VIDEOS_DIR, "*.mp4")) + \
                      glob.glob(os.path.join(MILITARY_VIDEOS_DIR, "*.mov")) + \
                      glob.glob(os.path.join(MILITARY_VIDEOS_DIR, "*.mkv"))
        if not video_files:
            raise FileNotFoundError(f"No video files found in {MILITARY_VIDEOS_DIR}")
        video_file = random.choice(video_files)
        
    print(f"\n[*] Selected Source Video: {video_file}")
    source_duration = get_video_duration(video_file)
    print(f"[*] Source Video Duration: {source_duration:.2f} seconds")
    
    if source_duration <= target_duration:
        start_time = 0.0
        clip_duration = source_duration
    else:
        max_start = max(0.0, source_duration - target_duration)
        start_time = round(random.uniform(0, max_start * 0.5), 1)
        clip_duration = min(target_duration, source_duration - start_time)
        
    print(f"[*] Extracting segment: {start_time:.1f}s to {start_time + clip_duration:.1f}s ({clip_duration:.1f}s total)")
    
    if not search_term:
        search_term = random.choice(["epic hybrid action trailer", "war cinematic trailer", "explosive blockbuster action"])
    
    music_track = fetch_epidemic_action_track(search_term)
    if not music_track:
        raise RuntimeError("Failed to fetch music track from Epidemic Sound.")
        
    music_path = music_track['local_path']
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    video_name = Path(video_file).stem
    output_path = os.path.join(OUTPUT_DIR, f"US_Military_Trailer_{video_name}_{timestamp}.mp4")
    
    print("\n-------------------------------------------------------")
    print(f" FFMPEG MOVIE TRAILER COMPOSITOR (Track: \"{music_track['title']}\")")
    print("-------------------------------------------------------")
    print(f"[*] Output Destination: {output_path}")
    
    fade_start = max(0.0, clip_duration - 2.0)
    
    v_filter = (
        "crop=w=ih*9/16:h=ih:x=(iw-ih*9/16)/2:y=0,"
        "scale=1080:1920:flags=bicubic,"
        "eq=contrast=1.14:saturation=1.18:gamma=0.95,"
        f"fade=t=in:st=0:d=1.0,fade=t=out:st={fade_start}:d=2.0[v]"
    )
    
    # Enhanced Audio Filter Chain: Sub-bass boost + Treble clarity + Loudness normalization
    a_filter = "bass=g=6:f=60,treble=g=3:f=4000,loudnorm=I=-14:TP=-1.5:LRA=11"
    
    if audio_mode == "replace":
        filter_complex = (
            f"[0:v]{v_filter}; "
            f"[1:a]volume=1.0,{a_filter},afade=t=out:st={fade_start}:d=2.0[a]"
        )
    else:
        filter_complex = (
            f"[0:v]{v_filter}; "
            f"[0:a]volume=0.8,afade=t=out:st={fade_start}:d=2.0[a_native]; "
            f"[1:a]volume=0.6,{a_filter},afade=t=out:st={fade_start}:d=2.0[a_music]; "
            f"[a_native][a_music]amix=inputs=2:duration=first:dropout_transition=2:normalize=0[a]"
        )
        
    ffmpeg_cmd = [
        FFMPEG_PATH, "-y",
        "-ss", str(start_time),
        "-t", str(clip_duration),
        "-i", video_file,
        "-i", music_path,
        "-filter_complex", filter_complex,
        "-map", "[v]",
        "-map", "[a]",
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "17",
        "-c:a", "aac",
        "-b:a", "256k",
        "-shortest",
        output_path
    ]
    
    print("[*] Running FFmpeg render pipeline...")
    render_start = time.time()
    res = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
    render_time = time.time() - render_start
    
    if res.returncode != 0:
        print(f"[!] FFmpeg Error:\n{res.stderr}")
        raise RuntimeError("FFmpeg render failed!")
        
    output_bytes = os.path.getsize(output_path)

    print(f"[+] Render Completed in {render_time:.1f} seconds!")
    print(f"[+] Output Short Size: {output_bytes / (1024*1024):.2f} MB")
    print(f"[+] Saved to: {output_path}")
    print("-------------------------------------------------------\n")
    return output_path

def batch_military_shorts(video_file: str = None, num_shorts: int = 3, target_duration: float = 35.0, audio_mode: str = "replace"):
    """
    Slices long-form military video into multiple distinct shorts across different time ranges.
    """
    if not video_file or not os.path.exists(video_file):
        video_files = glob.glob(os.path.join(MILITARY_VIDEOS_DIR, "*.mp4"))
        if not video_files:
            raise FileNotFoundError(f"No video files found in {MILITARY_VIDEOS_DIR}")
        video_file = random.choice(video_files)
        
    source_duration = get_video_duration(video_file)
    print(f"\n[*] BATCH PROCESSING Long-Form Video: {video_file} ({source_duration:.1f}s total)")
    
    # Divide duration into distinct chunks
    step = source_duration / num_shorts
    outputs = []
    
    for i in range(num_shorts):
        start = round(i * step, 1)
        dur = min(target_duration, source_duration - start)
        if dur < 10.0:
            continue
        print(f"\n---> Generating Short #{i+1} of {num_shorts} (Start: {start}s, Duration: {dur}s)...")
        
        # Select random search term for each batch item
        term = random.choice(EPIDEMIC_ACTION_SEARCH_TERMS)
        
        # Override calculation inside build_military_short by calling ffmpeg directly or customizing
        music_track = fetch_epidemic_action_track(term)
        if not music_track:
            continue
            
        music_path = music_track['local_path']
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        video_name = Path(video_file).stem
        output_path = os.path.join(OUTPUT_DIR, f"US_Military_Trailer_{video_name}_Part{i+1}_{timestamp}.mp4")
        fade_start = max(0.0, dur - 2.0)
        
        if audio_mode == "replace":
            filter_complex = (
                f"[0:v]crop=w=ih*9/16:h=ih:x=(iw-ih*9/16)/2:y=0,scale=1080:1920:flags=bicubic[v]; "
                f"[1:a]volume=1.0,afade=t=out:st={fade_start}:d=2.0[a]"
            )
        else:
            filter_complex = (
                f"[0:v]crop=w=ih*9/16:h=ih:x=(iw-ih*9/16)/2:y=0,scale=1080:1920:flags=bicubic[v]; "
                f"[0:a]volume=0.8,afade=t=out:st={fade_start}:d=2.0[a_native]; "
                f"[1:a]volume=0.6,afade=t=out:st={fade_start}:d=2.0[a_music]; "
                f"[a_native][a_music]amix=inputs=2:duration=first:dropout_transition=2:normalize=0[a]"
            )
            
        ffmpeg_cmd = [
            FFMPEG_PATH, "-y",
            "-ss", str(start),
            "-t", str(dur),
            "-i", video_file,
            "-i", music_path,
            "-filter_complex", filter_complex,
            "-map", "[v]",
            "-map", "[a]",
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "18",
            "-c:a", "aac",
            "-b:a", "192k",
            "-shortest",
            output_path
        ]
        
        res = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
        if res.returncode == 0:
            print(f"[+] Short #{i+1} Rendered Successfully -> {output_path}")
            outputs.append(output_path)
            
    return outputs

def build_military_longform(video_file: str = None, search_term: str = None, audio_mode: str = "replace", vertical: bool = False, cinematic: bool = True):
    """
    Processes full-length video (full duration, e.g. 16:9 widescreen or 9:16 vertical)
    with Epidemic Sound trailer music (NO text, NO voiceover).
    Includes optional Cinematic Color Grading, Audio Loudness Normalization, and Smooth Fades.
    """
    if not video_file or not os.path.exists(video_file):
        video_files = glob.glob(os.path.join(MILITARY_VIDEOS_DIR, "*.mp4"))
        if not video_files:
            raise FileNotFoundError(f"No video files found in {MILITARY_VIDEOS_DIR}")
        video_file = random.choice(video_files)
        
    source_duration = get_video_duration(video_file)
    print(f"\n[*] PROCESSING FULL-LENGTH VIDEO: {video_file} ({source_duration:.2f}s total duration)")
    
    if not search_term:
        search_term = random.choice(EPIDEMIC_ACTION_SEARCH_TERMS)
        
    music_track = fetch_epidemic_action_track(search_term)
    if not music_track:
        raise RuntimeError("Failed to fetch music track from Epidemic Sound.")
        
    music_path = music_track['local_path']
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    video_name = Path(video_file).stem
    aspect_tag = "9x16" if vertical else ("16x9_Cinematic" if cinematic else "16x9")
    output_path = os.path.join(OUTPUT_DIR, f"US_Military_Full_{aspect_tag}_{video_name}_{timestamp}.mp4")
    
    print("\n-------------------------------------------------------")
    print(f" FFMPEG CINEMATIC BLOCKBUSTER COMPOSITOR ({aspect_tag.upper()}, Duration: {source_duration:.1f}s)")
    print("-------------------------------------------------------")
    print(f"[*] Output Destination: {output_path}")
    
    fade_start = max(0.0, source_duration - 3.0)
    
    # Visual Filters: Color grading (contrast, saturation, gamma) + Smooth video fade in/out
    if vertical:
        v_filter = (
            f"crop=w=ih*9/16:h=ih:x=(iw-ih*9/16)/2:y=0,scale=1080:1920:flags=bicubic"
        )
    else:
        v_filter = "scale=1920:1080:flags=bicubic"
        
    if cinematic:
        # Action movie color grade: +12% contrast, +15% saturation, darker shadows, 1s fade in, 3s fade out
        v_filter += f",eq=contrast=1.12:saturation=1.15:gamma=0.96,fade=t=in:st=0:d=1.0,fade=t=out:st={fade_start}:d=3.0"
        
    v_filter += "[v]"
        
    # Audio Filters: Loudness normalization + Fade Out
    if audio_mode == "replace":
        filter_complex = (
            f"[0:v]{v_filter}; "
            f"[1:a]volume=1.0,loudnorm=I=-14:TP=-1.5:LRA=11,afade=t=out:st={fade_start}:d=3.0[a]"
        )
    else:
        filter_complex = (
            f"[0:v]{v_filter}; "
            f"[0:a]volume=0.8,afade=t=out:st={fade_start}:d=3.0[a_native]; "
            f"[1:a]volume=0.6,loudnorm=I=-14:TP=-1.5:LRA=11,afade=t=out:st={fade_start}:d=3.0[a_music]; "
            f"[a_native][a_music]amix=inputs=2:duration=first:dropout_transition=2:normalize=0[a]"
        )
        
    ffmpeg_cmd = [
        FFMPEG_PATH, "-y",
        "-i", video_file,
        "-stream_loop", "-1", "-i", music_path,
        "-filter_complex", filter_complex,
        "-map", "[v]",
        "-map", "[a]",
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "17",
        "-c:a", "aac",
        "-b:a", "256k",
        "-t", str(source_duration),
        output_path
    ]
    
    print("[*] Running FFmpeg Cinematic Blockbuster render pipeline...")
    render_start = time.time()
    res = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
    render_time = time.time() - render_start
    
    if res.returncode != 0:
        print(f"[!] FFmpeg Error:\n{res.stderr}")
        raise RuntimeError("FFmpeg render failed!")
        
    output_bytes = os.path.getsize(output_path)
    print(f"[+] Render Completed in {render_time:.1f} seconds!")
    print(f"[+] Output File Size: {output_bytes / (1024*1024):.2f} MB")
    print(f"[+] Saved to: {output_path}")
    print("-------------------------------------------------------\n")
    return output_path

def build_military_hollywood_edit(video_file: str = None, search_term: str = None, audio_mode: str = "mix", speedramp: bool = True):
    """
    Renders Hollywood Kinetic Blockbuster Edit for long-form / short videos with:
    1. 2.35:1 Anamorphic Scope Letterboxing (Cinematic top/bottom bars)
    2. Optional Dynamic Speed Ramping or Smooth Full-Length Processing
    3. Low-Volume Natural Jet/Engine Audio (25%) + Super Action Epidemic Sound Soundtrack (85%)
    4. Sub-Bass Boost + Treble Clarity + EBU R128 Loudness Normalization
    5. Zero Voiceover, Zero Text.
    """
    if not video_file or not os.path.exists(video_file):
        video_files = glob.glob(os.path.join(MILITARY_VIDEOS_DIR, "*.mp4"))
        if not video_files:
            raise FileNotFoundError(f"No video files found in {MILITARY_VIDEOS_DIR}")
        video_file = random.choice(video_files)
        
    source_duration = get_video_duration(video_file)
    print(f"\n[*] PROCESSING HOLLYWOOD KINETIC EDIT: {video_file} ({source_duration:.2f}s total duration)")
    
    if not search_term:
        search_term = "epic hybrid action trailer"
        
    music_track = fetch_epidemic_action_track(search_term)
    if not music_track:
        raise RuntimeError("Failed to fetch music track from Epidemic Sound.")
        
    music_path = music_track['local_path']
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    video_name = Path(video_file).stem
    mode_tag = "Hollywood_HollywoodScope_15min"
    output_path = os.path.join(OUTPUT_DIR, f"US_Military_Hollywood_{video_name}_{timestamp}.mp4")
    
    print("\n-------------------------------------------------------")
    print(f" FFMPEG HOLLYWOOD BLOCKBUSTER COMPOSITOR ({mode_tag}, Duration: {source_duration:.1f}s)")
    print("-------------------------------------------------------")
    print(f"[*] Output Destination: {output_path}")
    
    fade_start = max(0.0, source_duration - 3.0)
    
    v_base = (
        "scale=1920:1080:flags=bicubic,"
        "eq=contrast=1.14:saturation=1.18:gamma=0.95,"
        "drawbox=x=0:y=0:w=iw:h=132:color=black:t=fill,"
        "drawbox=x=0:y=ih-132:w=iw:h=132:color=black:t=fill,"
        f"fade=t=in:st=0:d=1.0,fade=t=out:st={fade_start}:d=3.0"
    )
    
    a_filter = "bass=g=6:f=60,treble=g=3:f=4000,loudnorm=I=-14:TP=-1.5:LRA=11"
    
    if audio_mode == "replace":
        audio_complex = f"[1:a]volume=1.0,{a_filter},afade=t=out:st={fade_start}:d=3.0[a]"
    else:
        # Mix lowered natural jet audio (25% volume) with super action music (85% volume)
        audio_complex = (
            f"[0:a]volume=0.25,afade=t=out:st={fade_start}:d=3.0[a_native]; "
            f"[1:a]volume=0.85,{a_filter},afade=t=out:st={fade_start}:d=3.0[a_music]; "
            f"[a_native][a_music]amix=inputs=2:duration=first:dropout_transition=2:normalize=0[a]"
        )
        
    filter_complex = f"[0:v]{v_base}[v]; {audio_complex}"
        
    ffmpeg_cmd = [
        FFMPEG_PATH, "-y",
        "-i", video_file,
        "-stream_loop", "-1", "-i", music_path,
        "-filter_complex", filter_complex,
        "-map", "[v]",
        "-map", "[a]",
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "17",
        "-c:a", "aac",
        "-b:a", "256k",
        "-t", str(source_duration),
        output_path
    ]
    
    print("[*] Running FFmpeg Hollywood Blockbuster render pipeline...")
    render_start = time.time()
    res = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
    render_time = time.time() - render_start
    
    if res.returncode != 0:
        print(f"[!] FFmpeg Error:\n{res.stderr}")
        raise RuntimeError("FFmpeg render failed!")
        
    output_bytes = os.path.getsize(output_path)
    print(f"[+] Blockbuster Render Completed in {render_time:.1f} seconds!")
    print(f"[+] Output File Size: {output_bytes / (1024*1024):.2f} MB")
    print(f"[+] Saved to: {output_path}")
    print("-------------------------------------------------------\n")
    return output_path


def combine_military_videos(video_files: list, search_term: str = None, audio_mode: str = "replace", vertical: bool = True):
    """
    Seamlessly concatenates multiple military video files into a combined action short.
    """
    valid_files = [f for f in video_files if os.path.exists(f)]
    if not valid_files:
        raise FileNotFoundError("None of the specified video files exist.")
        
    print(f"\n[*] COMBINING {len(valid_files)} VIDEO CLIPS:")
    total_duration = 0.0
    for vf in valid_files:
        dur = get_video_duration(vf)
        total_duration += dur
        print(f"  - {vf} ({dur:.2f}s)")
        
    print(f"[*] Total Combined Duration: {total_duration:.2f} seconds")
    
    if not search_term:
        search_term = random.choice(EPIDEMIC_ACTION_SEARCH_TERMS)
        
    music_track = fetch_epidemic_action_track(search_term)
    if not music_track:
        raise RuntimeError("Failed to fetch music track from Epidemic Sound.")
        
    music_path = music_track['local_path']
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    output_path = os.path.join(OUTPUT_DIR, f"US_Military_Combined_Short_{timestamp}.mp4")
    
    fade_start = max(0.0, total_duration - 2.0)
    
    # Construct input flags & filter graph for concatenation
    inputs = []
    filter_parts = []
    
    for i, vf in enumerate(valid_files):
        inputs.extend(["-i", vf])
        if vertical:
            crop_filter = "crop=w=ih*9/16:h=ih:x=(iw-ih*9/16)/2:y=0,scale=1080:1920:flags=bicubic"
        else:
            crop_filter = "scale=1920:1080:flags=bicubic"
            
        filter_parts.append(f"[{i}:v]setpts=PTS-STARTPTS,{crop_filter},eq=contrast=1.14:saturation=1.18:gamma=0.95[v{i}];")
        
    v_concat = "".join([f"[v{i}]" for i in range(len(valid_files))])
    v_filter = f"{v_concat}concat=n={len(valid_files)}:v=1:a=0,fps=30,fade=t=in:st=0:d=1.0,fade=t=out:st={fade_start}:d=2.0[v]"
    
    filter_complex = "".join(filter_parts) + v_filter + f"; [{len(valid_files)}:a]bass=g=6:f=60,volume=1.0,loudnorm=I=-14:TP=-1.5:LRA=11,afade=t=out:st={fade_start}:d=2.0[a]"
    
    ffmpeg_cmd = [
        FFMPEG_PATH, "-y",
        *inputs,
        "-i", music_path,
        "-filter_complex", filter_complex,
        "-map", "[v]",
        "-map", "[a]",
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "17",
        "-c:a", "aac",
        "-b:a", "256k",
        "-t", str(total_duration),
        output_path
    ]
    
    print("\n-------------------------------------------------------")
    print(f" FFMPEG COMBINED SHORT COMPOSITOR (Total Duration: {total_duration:.1f}s)")
    print("-------------------------------------------------------")
    print(f"[*] Output Destination: {output_path}")
    print("[*] Running FFmpeg render pipeline...")
    
    render_start = time.time()
    res = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
    render_time = time.time() - render_start
    
    if res.returncode != 0:
        print(f"[!] FFmpeg Error:\n{res.stderr}")
        raise RuntimeError("FFmpeg render failed!")
        
    output_bytes = os.path.getsize(output_path)
    print("[+] Combined Render Completed in {render_time:.1f} seconds!")
    print(f"[+] Output Short Size: {output_bytes / (1024*1024):.2f} MB")
    print(f"[+] Saved to: {output_path}")
    print("-------------------------------------------------------\n")
    return output_path

def build_b2_action_only_short(video_file: str = None, search_term: str = None, audio_mode: str = "replace", vertical: bool = True):
    """
    Renders full-length B-2 Stealth Bomber edit (77 seconds duration) with ALL human bodies and body parts removed (0% humans),
    leaving 100% pure B-2 Stealth Bomber aircraft footage paired with an explosive orchestral war score.
    """
    if not video_file or not os.path.exists(video_file):
        video_file = os.path.join(MILITARY_VIDEOS_DIR, "DOD_111608478.mp4")
        if not os.path.exists(video_file):
            raise FileNotFoundError(f"Video file not found: {video_file}")
            
    print(f"\n[*] PROCESSING 100% HUMAN-FREE B-2 STEALTH BOMBER EDIT: {video_file}")
    
    # 100% Pure B-2 Stealth Bomber Aircraft Segment (0% humans / human body parts):
    # Segment: 0.0s - 77.0s (77.0s continuous pure B-2 Stealth Bomber takeoff, climb & in-flight maneuvers)
    start_time = 0.0
    clip_duration = 77.0
    
    print(f"[*] Total Pure B-2 Aircraft Duration: {clip_duration:.2f} seconds (0% Human Bodies / 0% Human Parts)")
    
    if not search_term:
        search_term = "epic orchestral action trailer"
        
    music_track = fetch_epidemic_action_track(search_term)
    if not music_track:
        raise RuntimeError("Failed to fetch music track from Epidemic Sound.")
        
    music_path = music_track['local_path']
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    output_filename = f"US_Military_B2_Pure_NoHumans_77s_{timestamp}.mp4"
    output_path = os.path.join(OUTPUT_DIR, output_filename)
    
    fade_start = max(0.0, clip_duration - 3.0)
    
    if vertical:
        crop_filter = "crop=w=ih*9/16:h=ih:x=(iw-ih*9/16)/2:y=0,scale=1080:1920:flags=bicubic"
    else:
        crop_filter = "scale=1920:1080:flags=bicubic"
        
    v_filter = (
        f"[0:v]trim={start_time}:{clip_duration},setpts=(PTS-STARTPTS)*1.0,{crop_filter},"
        f"eq=contrast=1.14:saturation=1.18:gamma=0.95,"
        f"fade=t=in:st=0:d=1.0,fade=t=out:st={fade_start}:d=3.0[v]"
    )
    
    a_filter = "bass=g=6:f=60,treble=g=3:f=4000,loudnorm=I=-14:TP=-1.5:LRA=11"
    
    if audio_mode == "replace":
        filter_complex = f"{v_filter}; [1:a]volume=1.0,{a_filter},afade=t=out:st={fade_start}:d=3.0[a]"
    else:
        filter_complex = f"{v_filter}; [0:a]volume=0.25,afade=t=out:st={fade_start}:d=3.0[a_native]; [1:a]volume=0.85,{a_filter},afade=t=out:st={fade_start}:d=3.0[a_music]; [a_native][a_music]amix=inputs=2:duration=first:dropout_transition=2:normalize=0[a]"
        
    ffmpeg_cmd = [
        FFMPEG_PATH, "-y",
        "-i", video_file,
        "-stream_loop", "-1", "-i", music_path,
        "-filter_complex", filter_complex,
        "-map", "[v]",
        "-map", "[a]",
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "17",
        "-c:a", "aac",
        "-b:a", "256k",
        "-t", str(clip_duration),
        output_path
    ]
    
    print("\n-------------------------------------------------------")
    print(f" FFMPEG PURE B-2 AIRCRAFT COMPOSITOR (0% Humans, Duration: {clip_duration:.1f}s @ 60fps)")
    print("-------------------------------------------------------")
    print(f"[*] Output Destination: {output_path}")
    print("[*] Running FFmpeg render pipeline...")
    
    render_start = time.time()
    res = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
    render_time = time.time() - render_start
    
    if res.returncode != 0:
        print(f"[!] FFmpeg Error:\n{res.stderr}")
        raise RuntimeError("FFmpeg render failed!")
        
    output_bytes = os.path.getsize(output_path)
    print(f"[+] B-2 Pure Aircraft Render Completed in {render_time:.1f} seconds!")
    print(f"[+] Output File Size: {output_bytes / (1024*1024):.2f} MB")
    print(f"[+] Saved to: {output_path}")
    print("-------------------------------------------------------\n")
    return output_path


def build_hooked_military_short(video_file: str = None, hook_range: tuple = (45.0, 48.0), main_segments: list = None, search_term: str = None, audio_mode: str = "replace", vertical: bool = True):
    """
    Renders an action short using the NEW EDITING STYLE with STRICT 0% FACES GUARANTEE:
    1. 3.0-Second Retention Hook Engine: Places peak action clip at Frame 0 (0.0s - 3.0s) to stop scrolling.
    2. Strict Face Removal: Completely trims out 0.0s-23.5s (tarmac human faces + pilot cockpit face closeups).
    3. Epic Hybrid Orchestral Score (Hans Zimmer Style): Deep brass swells, massive impacts, tension strings.
    """
    if not video_file or not os.path.exists(video_file):
        video_file = os.path.join(MILITARY_VIDEOS_DIR, "DOD_107190749.mp4")
        if not os.path.exists(video_file):
            raise FileNotFoundError(f"Video file not found: {video_file}")
            
    if main_segments is None:
        # Strictly face-free segments (excludes all 0.0s - 23.5s human faces)
        main_segments = [(24.0, 45.0), (48.0, 59.5)]
        
    print(f"\n[*] PROCESSING STRICT 0% FACES SHORT (WITH 3.0-SEC RETENTION HOOK): {video_file}")
    
    hook_dur = hook_range[1] - hook_range[0]
    main_dur = sum(seg[1] - seg[0] for seg in main_segments)
    total_dur = hook_dur + main_dur
    print(f"[*] Hook Duration: {hook_dur:.1f}s | Main Action Duration: {main_dur:.1f}s | Total Short Duration: {total_dur:.1f}s (100% Zero Faces Guarantee)")
    
    if not search_term:
        search_term = "hans zimmer cinematic trailer"
        
    music_track = fetch_epidemic_action_track(search_term)
    if not music_track:
        raise RuntimeError("Failed to fetch music track from Epidemic Sound.")
        
    music_path = music_track['local_path']
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    output_filename = f"US_Military_StrictNoFaces_HookedShort_{Path(video_file).stem}_{timestamp}.mp4"
    output_path = os.path.join(OUTPUT_DIR, output_filename)
    
    fade_start = max(0.0, total_dur - 2.5)
    
    if vertical:
        crop_filter = "crop=w=ih*9/16:h=ih:x=(iw-ih*9/16)/2:y=0,scale=1080:1920:flags=bicubic"
    else:
        crop_filter = "scale=1920:1080:flags=bicubic"
        
    filter_parts = []
    # 3-second Hook at Frame 0
    filter_parts.append(
        f"[0:v]trim={hook_range[0]}:{hook_range[1]},setpts=(PTS-STARTPTS)*1.0,{crop_filter},"
        f"eq=contrast=1.14:saturation=1.18:gamma=0.95[v_hook];"
    )
    # Main segments
    for idx, (st, et) in enumerate(main_segments):
        filter_parts.append(
            f"[0:v]trim={st}:{et},setpts=(PTS-STARTPTS)*1.0,{crop_filter},"
            f"eq=contrast=1.14:saturation=1.18:gamma=0.95[v_seg_{idx}];"
        )
        
    concat_inputs = "[v_hook]" + "".join([f"[v_seg_{i}]" for i in range(len(main_segments))])
    total_clips = 1 + len(main_segments)
    v_concat = f"{concat_inputs}concat=n={total_clips}:v=1:a=0,fade=t=in:st=0:d=0.5,fade=t=out:st={fade_start}:d=2.5[v]"
    
    a_filter = "bass=g=6:f=60,treble=g=3:f=4000,loudnorm=I=-14:TP=-1.5:LRA=11"
    
    filter_complex = "".join(filter_parts) + f" {v_concat}; [1:a]volume=1.0,{a_filter},afade=t=out:st={fade_start}:d=2.5[a]"
        
    ffmpeg_cmd = [
        FFMPEG_PATH, "-y",
        "-i", video_file,
        "-i", music_path,
        "-filter_complex", filter_complex,
        "-map", "[v]",
        "-map", "[a]",
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "17",
        "-c:a", "aac",
        "-b:a", "256k",
        "-t", str(total_dur),
        output_path
    ]
    
    print("\n-------------------------------------------------------")
    print(f" FFMPEG STRICT 0% FACES SHORT COMPOSITOR (3.0s Hook, Duration: {total_dur:.1f}s)")
    print("-------------------------------------------------------")
    print(f"[*] Output Destination: {output_path}")
    print("[*] Running FFmpeg render pipeline...")
    
    render_start = time.time()
    res = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
    render_time = time.time() - render_start
    
    if res.returncode != 0:
        print(f"[!] FFmpeg Error:\n{res.stderr}")
        raise RuntimeError("FFmpeg render failed!")
        
    output_bytes = os.path.getsize(output_path)
    print(f"[+] Strict No-Faces Short Render Completed in {render_time:.1f} seconds!")
    print(f"[+] Output Short Size: {output_bytes / (1024*1024):.2f} MB")
    print(f"[+] Saved to: {output_path}")
    print("-------------------------------------------------------\n")
    return output_path



def generate_6_iran_shorts(audio_mode: str = "replace"):


    """
    Batch generates 6 action-packed 9:16 vertical shorts from Iran strike videos
    using pure orchestral war soundtracks (NO techno, NO voiceover, NO text).
    """
    candidate_videos = [
        os.path.join(MILITARY_VIDEOS_DIR, "DOD_106590558.mp4"),
        os.path.join(MILITARY_VIDEOS_DIR, "DOD_111558669.mp4"),
        os.path.join(MILITARY_VIDEOS_DIR, "DOD_111615058.mp4"),
        os.path.join(MILITARY_VIDEOS_DIR, "DOD_111615082.mp4"),
        os.path.join(MILITARY_VIDEOS_DIR, "DOD_111615087.mp4"),
        os.path.join(MILITARY_VIDEOS_DIR, "DOD_111835497.mp4")
    ]
    
    orchestral_queries = [
        "epic orchestral action trailer",
        "cinematic orchestral war trailer",
        "heavy brass epic trailer",
        "orchestral action blockbuster",
        "cinematic orchestral war trailer",
        "epic orchestral action trailer"
    ]
    
    print("\n=======================================================")
    print(" BATCH GENERATING 6 ACTION-PACKED IRAN STRIKE SHORTS   ")
    print("=======================================================")
    
    rendered_shorts = []
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    
    for i, vf in enumerate(candidate_videos):
        if not os.path.exists(vf):
            print(f"[!] Warning: Video file not found: {vf}")
            continue
            
        dur = get_video_duration(vf)
        target_dur = min(35.0, dur)
        query = orchestral_queries[i % len(orchestral_queries)]
        
        print(f"\n---> Generating Short #{i+1} of 6: {Path(vf).name} ({dur:.1f}s total)...")
        
        music_track = fetch_epidemic_action_track(query)
        if not music_track:
            print(f"[!] Skipping Short #{i+1} due to music fetch issue.")
            continue
            
        music_path = music_track['local_path']
        output_filename = f"US_Military_IranStrikes_Short_{i+1}_{Path(vf).stem}_{timestamp}.mp4"
        output_path = os.path.join(OUTPUT_DIR, output_filename)
        
        fade_start = max(0.0, target_dur - 2.0)
        
        v_filter = (
            "crop=w=ih*9/16:h=ih:x=(iw-ih*9/16)/2:y=0,"
            "scale=1080:1920:flags=bicubic,"
            "eq=contrast=1.14:saturation=1.18:gamma=0.95,"
            f"fade=t=in:st=0:d=1.0,fade=t=out:st={fade_start}:d=2.0[v]"
        )
        
        a_filter = "bass=g=6:f=60,treble=g=3:f=4000,loudnorm=I=-14:TP=-1.5:LRA=11"
        
        if audio_mode == "replace":
            filter_complex = f"[0:v]{v_filter}; [1:a]volume=1.0,{a_filter},afade=t=out:st={fade_start}:d=2.0[a]"
        else:
            filter_complex = (
                f"[0:v]{v_filter}; "
                f"[0:a]volume=0.25,afade=t=out:st={fade_start}:d=2.0[a_native]; "
                f"[1:a]volume=0.85,{a_filter},afade=t=out:st={fade_start}:d=2.0[a_music]; "
                f"[a_native][a_music]amix=inputs=2:duration=first:dropout_transition=2:normalize=0[a]"
            )
            
        ffmpeg_cmd = [
            FFMPEG_PATH, "-y",
            "-t", str(target_dur),
            "-i", vf,
            "-i", music_path,
            "-filter_complex", filter_complex,
            "-map", "[v]",
            "-map", "[a]",
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "17",
            "-c:a", "aac",
            "-b:a", "256k",
            "-shortest",
            output_path
        ]
        
        res = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
        if res.returncode == 0:
            bytes_sz = os.path.getsize(output_path)
            print(f"[+] Short #{i+1} Rendered Successfully ({bytes_sz / (1024*1024):.2f} MB) -> {output_path}")
            rendered_shorts.append(output_path)
        else:
            print(f"[!] Short #{i+1} FFmpeg Render Error:\n{res.stderr}")
            
if __name__ == "__main__":
    import sys
    mode = sys.argv[1] if len(sys.argv) > 1 else "replace"
    if "--hook" in sys.argv or "--newstyle" in sys.argv:
        vf = sys.argv[2] if len(sys.argv) > 2 and os.path.exists(sys.argv[2]) else os.path.join(MILITARY_VIDEOS_DIR, "DOD_107190749.mp4")
        build_hooked_military_short(vf, audio_mode=mode)
    elif "--b2pure" in sys.argv or "--nopeople" in sys.argv:
        build_b2_action_only_short(os.path.join(MILITARY_VIDEOS_DIR, "DOD_111608478.mp4"), audio_mode=mode)
    elif "--iran6" in sys.argv or "--6shorts" in sys.argv:
        generate_6_iran_shorts(audio_mode=mode)
    elif "--combine" in sys.argv:
        files = [
            os.path.join(MILITARY_VIDEOS_DIR, "DOD_111615046.mp4"),
            os.path.join(MILITARY_VIDEOS_DIR, "DOD_111558644.mp4")
        ]
        combine_military_videos(files, audio_mode=mode)
    elif "--hollywood" in sys.argv or "--scope" in sys.argv or "--speedramp" in sys.argv:
        build_military_hollywood_edit(os.path.join(MILITARY_VIDEOS_DIR, "DOD_111856261.mp4"), audio_mode=mode, speedramp=True)
    elif "--long" in sys.argv or "--full" in sys.argv:
        is_vert = "--vertical" in sys.argv
        is_cinematic = "--raw" not in sys.argv
        build_military_longform(os.path.join(MILITARY_VIDEOS_DIR, "DOD_111856261.mp4"), audio_mode=mode, vertical=is_vert, cinematic=is_cinematic)
    elif "--batch" in sys.argv:
        batch_military_shorts(os.path.join(MILITARY_VIDEOS_DIR, "DOD_111856261.mp4"), num_shorts=3, audio_mode=mode)
    else:
        build_military_short(os.path.join(MILITARY_VIDEOS_DIR, "DOD_107190749.mp4"), audio_mode=mode)
