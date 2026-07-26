import requests
import subprocess
import time
import os
import json
import glob
import asyncio
import re
import random
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

VOICEBOX_URL = os.getenv('VOICEBOX_URL', 'http://127.0.0.1:17493')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY')
EPIDEMIC_SOUND_API_KEY = os.getenv('EPIDEMIC_SOUND_API_KEY')
FFMPEG_PATH = 'ffmpeg'

# Directories. MEDIA_ROOT is where your source footage lives; the per-category
# folders can be overridden individually. Set these in .env — see .env.example.
PROJECT_ROOT = Path(__file__).resolve().parent
MEDIA_ROOT = os.getenv('MEDIA_ROOT', str(PROJECT_ROOT / 'media'))

LIFE_VIDEOS_DIR = os.getenv('LIFE_VIDEOS_DIR', os.path.join(MEDIA_ROOT, 'Life'))
NATURE_VIDEOS_DIR = os.getenv('NATURE_VIDEOS_DIR', os.path.join(MEDIA_ROOT, 'Nature'))
GAMING_VIDEOS_DIR = os.getenv('GAMING_VIDEOS_DIR', os.path.join(MEDIA_ROOT, 'Gaming'))
BATMAN_VIDEOS_DIR = GAMING_VIDEOS_DIR
EPIDEMIC_MUSIC_DIR = os.getenv('EPIDEMIC_MUSIC_DIR', str(PROJECT_ROOT / 'assets' / 'epidemic_sound'))
OUTPUT_DIR = os.getenv('OUTPUT_DIR', str(PROJECT_ROOT / 'output'))

os.makedirs(LIFE_VIDEOS_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(EPIDEMIC_MUSIC_DIR, exist_ok=True)

# Morgan Freeman / Documentary Voice Persona Configuration
MORGAN_FREEMAN_VOICE = "en-US-ChristopherNeural"
MORGAN_FREEMAN_PITCH = "-2Hz"
MORGAN_FREEMAN_RATE = "-3%"

VIRAL_INSPIRATIONAL_QUOTES = [
    {
        "author": "Marcus Aurelius",
        "title": "What Stands in the Way Becomes the Way",
        "narration_script": "You have power over your mind... not outside events. [pause 1.0s] Realize this, and you will find UNSTOPPABLE strength. The impediment to action advances action. What stands in the way... BECOMES the way. Never let the future disturb you. You will meet it with the same weapons of reason that arm you today. Stand firm... and RECLAIM your destiny.",
        "search_term": "epic stoic orchestral motivation"
    },
    {
        "author": "Kobe Bryant",
        "title": "Pain is Temporary, Regret Lasts Forever",
        "narration_script": "Greatness is NOT for the faint of heart. [pause 1.0s] It requires sacrifice, relentless focus, and an absolute refusal to give up... when everything inside you screams to quit. Pain is TEMPORARY—regret lasts forever. Embrace the struggle, push past your limits, and DOMINATE your path.",
        "search_term": "mamba mentality action trailer"
    },
    {
        "author": "Steve Jobs",
        "title": "Here's to the Crazy Ones",
        "narration_script": "Here's to the crazy ones. The misfits. The rebels. The troublemakers. [pause 1.2s] The round pegs in the square holes. The ones who see things differently. They're not fond of rules, and they have no respect for the status quo. You can quote them, disagree with them, glorify or vilify them. About the only thing you can't do is IGNORE them. Because they change things. They push the human race forward. And while some may see them as the crazy ones, we see GENIUS. Because the people who are crazy enough to think they can change the world... are the ones who DO.",
        "search_term": "inspiring piano strings uplifting"
    }
]

INSPIRATIONAL_LLM_PROMPT = """
You are a master viral documentary scriptwriter specializing in 2026 high-retention 1M+ view Shorts & Reels.
Your theme is strictly SELF-DISCIPLINE & DAILY HARDSHIP (values discipline over motivation, no philosophy or stoicism labels). Given a topic, generate a hyper-realistic, punchy SCRIPT MONOLOGUE using 2026 script formatting rules:

Tone & Content Rules:
1. Theme: Self-Discipline & Daily Hardship (focus on painful daily execution, silent grinds, physical/mental friction, and relentless consistency).
2. NO toxic positivity, NO cliches (e.g. "believe in yourself", "reach for the stars", "follow your dreams").
3. DO NOT use generic AI words like "tapestry", "unwavering", "delve", "beacon", or "stoic".

Script Formatting Rules:
1. Spell out all numbers completely as words (e.g. "two thousand twenty-six" instead of "2026").
2. Use ellipses (...) to force reflective pauses, and em-dashes (—) for sudden dramatic rhythm shifts.
3. Strategically insert audio direction tags like [pause 1.5s] or [whisper] before serious, impactful sentences.
4. Capitalize single key impact verbs or adjectives for heavy vocal stress (e.g. "DOMINATES", "OUTWORK", "EXECUTE").
5. Include exact Epidemic Sound search parameters matching an intense, heavy, dark motivational mood.

Respond ONLY with valid JSON in the following format:
{
    "title": "Daily Hardship: The Price of Execution",
    "narration_script": "Motivation is a FLEETING mood. [pause 1.5s] When alarm rings at five in the morning... nobody is coming to push you. You gotta EXECUTE when your mind screams to stop. [whisper] Comfort is a slow trap. Suffer the raw friction of daily work... or drown in the quiet misery of regret.",
    "epidemic_search_term": "intense dark action trailer motivation"
}
"""

def spell_out_numbers(text: str) -> str:
    """Spells out numbers as words and normalizes dramatic punctuation for AI script pacing compliance."""
    num_map = {
        '0': 'zero', '1': 'one', '2': 'two', '3': 'three', '4': 'four',
        '5': 'five', '6': 'six', '7': 'seven', '8': 'eight', '9': 'nine',
        '10': 'ten', '2026': 'two thousand twenty-six', '2025': 'two thousand twenty-five',
        '100': 'one hundred', '1M': 'one million'
    }
    for k, v in num_map.items():
        text = re.sub(rf'\b{k}\b', v, text)
    # Normalize em-dashes and special unicode dashes to ' - ' to prevent word smushing
    text = text.replace('—', ' - ').replace('–', ' - ')
    return text

def fetch_and_download_epidemic_sound_track(search_term: str) -> dict:
    """Connects to Epidemic Sound Live Search API and downloads MP3 audio stream."""
    print('\n-------------------------------------------------------')
    print(f' EPIDEMIC SOUND API ENGINE (LIVE SEARCH & STREAM)')
    print('-------------------------------------------------------')
    print(f'[*] Querying Epidemic Sound Catalog for: "{search_term}"...')
    
    url = "https://www.epidemicsound.com/json/search/tracks/"
    headers = {
        'Authorization': f'Bearer {EPIDEMIC_SOUND_API_KEY}',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    params = {'term': search_term, 'limit': 8}
    
    try:
        res = requests.get(url, headers=headers, params=params, timeout=15)
        res.raise_for_status()
        data = res.json()
        tracks_dict = data.get('entities', {}).get('tracks', {})
        
        candidates = []
        for track_id, track in tracks_dict.items():
            stems = track.get('stems', {})
            full_stem = stems.get('full', {})
            mp3_url = full_stem.get('lqMp3Url')
            title = track.get('title', 'Unknown Track')
            isrc = track.get('isrc', 'N/A')
            creatives = track.get('creatives', {}).get('mainArtists', [])
            artist = creatives[0].get('name') if creatives else 'Epidemic Artist'
            if mp3_url:
                candidates.append({
                    'id': track_id,
                    'title': title,
                    'artist': artist,
                    'isrc': isrc,
                    'mp3_url': mp3_url
                })
                
        if candidates:
            selected_track = random.choice(candidates[:4])
            print(f"[+] Found {len(candidates)} matching Epidemic Sound tracks!")
            print(f"[+] SELECTED TRACK: \"{selected_track['title']}\" by {selected_track['artist']} (ISRC: {selected_track['isrc']})")
            
            clean_title = re.sub(r'[^\w\-_]', '_', selected_track['title'])
            download_path = os.path.join(EPIDEMIC_MUSIC_DIR, f"{clean_title}.mp3")
            
            if not os.path.exists(download_path):
                print(f"[*] Downloading audio stream from Epidemic Sound CDN...")
                audio_res = requests.get(selected_track['mp3_url'], timeout=30)
                with open(download_path, 'wb') as f:
                    f.write(audio_res.content)
                print(f"[+] Downloaded Epidemic Sound Track ({len(audio_res.content)} bytes) to:\n    {download_path}")
            else:
                print(f"[+] Using cached Epidemic Sound Track:\n    {download_path}")
                
            selected_track['local_path'] = download_path
            print('-------------------------------------------------------\n')
            return selected_track
    except Exception as err:
        print(f"[!] Epidemic Sound API Search Error: {err}")
        
    print('-------------------------------------------------------\n')
    return None

def get_all_target_videos() -> list:
    """Lists raw video files from Life and Nature directories."""
    videos = []
    if os.path.exists(LIFE_VIDEOS_DIR):
        videos.extend(glob.glob(os.path.join(LIFE_VIDEOS_DIR, "*.mp4")))
    if os.path.exists(NATURE_VIDEOS_DIR):
        videos.extend(glob.glob(os.path.join(NATURE_VIDEOS_DIR, "*.mp4")))
    return videos

def generate_inspirational_quote_script(topic: str, quote_index: int = 0) -> dict:
    """Connects to LLM for 2026 formatted electrifying inspirational quote."""
    print(f'[*] Connecting to LLM for 2026 Formatted Quote on: "{topic}"...')
    
    if OPENAI_API_KEY:
        try:
            url = 'https://api.openai.com/v1/chat/completions'
            headers = {
                'Authorization': f'Bearer {OPENAI_API_KEY}',
                'Content-Type': 'application/json'
            }
            payload = {
                'model': 'gpt-4o',
                'messages': [
                    {'role': 'system', 'content': INSPIRATIONAL_LLM_PROMPT},
                    {'role': 'user', 'content': f'Write a 2026 formatted electrifying inspirational quote script for: {topic}'}
                ],
                'response_format': {'type': 'json_object'},
                'temperature': 0.8
            }
            res = requests.post(url, headers=headers, json=payload, timeout=30)
            res.raise_for_status()
            content = res.json()['choices'][0]['message']['content']
            data = json.loads(content)
            print('[+] 2026 Formatted Quote generated via OpenAI GPT-4o!')
            return data
        except Exception as e:
            print(f'[!] OpenAI API failed: {e}. Trying Gemini API fallback...')

    if GOOGLE_API_KEY:
        try:
            url = f'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GOOGLE_API_KEY}'
            headers = {'Content-Type': 'application/json'}
            prompt_text = f"{INSPIRATIONAL_LLM_PROMPT}\n\nUser Request: Write a 2026 formatted electrifying inspirational quote script for: {topic}"
            payload = {
                'contents': [{'parts': [{'text': prompt_text}]}],
                'generationConfig': {'responseMimeType': 'application/json'}
            }
            res = requests.post(url, headers=headers, json=payload, timeout=30)
            res.raise_for_status()
            content = res.json()['candidates'][0]['content']['parts'][0]['text']
            data = json.loads(content)
            print('[+] 2026 Formatted Quote generated via Gemini 2.5 Flash!')
            return data
        except Exception as e:
            print(f'[!] Gemini API failed: {e}')

    return VIRAL_INSPIRATIONAL_QUOTES[quote_index % len(VIRAL_INSPIRATIONAL_QUOTES)]

def generate_silence_mp3(duration_seconds: float, output_path: str):
    """Generates a silent MP3 file of specified duration matching TTS audio format (24kHz mono)."""
    cmd = [
        FFMPEG_PATH, '-y',
        '-f', 'lavfi', '-i', 'anullsrc=r=24000:cl=mono',
        '-t', str(duration_seconds),
        '-c:a', 'libmp3lame',
        '-ar', '24000',
        '-ac', '1',
        '-b:a', '192k',
        output_path
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT, check=True)

def sanitize_text_for_human_tts(txt: str) -> str:
    """Sanitizes script text for TTS engine to prevent robotic vocal glitches, staccato spikes, and capitalization distortion."""
    txt = re.sub(r'[*_]', '', txt)
    txt = re.sub(r'\[.*?\]', '', txt)
    words = txt.split()
    clean_words = []
    for w in words:
        clean_word = re.sub(r'([A-Z]{2,})', lambda m: m.group(1).lower(), w)
        clean_words.append(clean_word)
    txt = " ".join(clean_words)
    txt = re.sub(r'\s+', ' ', txt).strip()
    return txt

def generate_voiceover_audio(script_text: str, filename_prefix: str) -> tuple[str, str]:
    """Generates voiceover using 2026 script formatting rules, dynamic micro-pauses, and baritone tuning."""
    print('[*] Generating 2026 Paced Baritone Voiceover with Micro-Pause Engine...')
    audio_mp3 = os.path.abspath(os.path.join(OUTPUT_DIR, f'temp_voice_2026_{filename_prefix}.mp3'))
    
    clean_text = spell_out_numbers(script_text)
    clean_text = re.sub(r"\[whisper\]", "", clean_text)
    clean_text = re.sub(r"\[breath\]", "...", clean_text)
    
    word_pause_map = {
        'one point five': '1.5',
        'one point two': '1.2',
        'one point zero': '1.0',
        'zero point five': '0.5',
        'one': '1.0',
        'two': '2.0',
        'three': '3.0'
    }
    def normalize_pause_tag(match):
        val_str = match.group(1).lower().strip()
        val_str = re.sub(r'seconds?', '', val_str).strip()
        if val_str in word_pause_map:
            return f"[pause {word_pause_map[val_str]}s]"
        try:
            float(val_str)
            return f"[pause {val_str}s]"
        except ValueError:
            return "[pause 1.0s]"

    clean_text = re.sub(r"\[pause\s+([^\]]+)\]", normalize_pause_tag, clean_text)
    
    pattern = r'\[pause\s*([\d\.]+)\s*s?\]'
    tokens = re.split(pattern, clean_text)
    
    segments = []
    i = 0
    while i < len(tokens):
        text_part = tokens[i].strip()
        pause_dur = None
        if i + 1 < len(tokens):
            try:
                pause_dur = float(tokens[i+1])
            except ValueError:
                pause_dur = None
        segments.append((text_part, pause_dur))
        i += 2

    import edge_tts
    
    audio_parts = []
    part_idx = 0
    
    for text_part, pause_dur in segments:
        if text_part:
            part_path = os.path.abspath(os.path.join(OUTPUT_DIR, f'temp_part_{filename_prefix}_{part_idx}.mp3'))
            tts_ready_text = sanitize_text_for_human_tts(text_part)
            async def run_edge_tts(txt, path):
                communicate = edge_tts.Communicate(
                    txt, 
                    MORGAN_FREEMAN_VOICE, 
                    pitch=MORGAN_FREEMAN_PITCH, 
                    rate=MORGAN_FREEMAN_RATE
                )
                await communicate.save(path)
            
            try:
                asyncio.run(run_edge_tts(tts_ready_text, part_path))
                if os.path.exists(part_path) and os.path.getsize(part_path) > 100:
                    audio_parts.append(part_path)
            except Exception as e:
                print(f"[!] Error generating TTS segment '{text_part[:20]}...': {e}")
                
        if pause_dur and pause_dur > 0.05:
            silence_path = os.path.abspath(os.path.join(OUTPUT_DIR, f'temp_silence_{filename_prefix}_{part_idx}.mp3'))
            try:
                generate_silence_mp3(pause_dur, silence_path)
                if os.path.exists(silence_path):
                    audio_parts.append(silence_path)
                    print(f"    [+] Inserted dramatic pause: {pause_dur}s")
            except Exception as e:
                print(f"[!] Error generating silence: {e}")
                
        part_idx += 1
        
    if not audio_parts:
        return None, "None"
        
    if len(audio_parts) == 1:
        if os.path.exists(audio_mp3):
            os.remove(audio_mp3)
        os.rename(audio_parts[0], audio_mp3)
    else:
        list_path = os.path.abspath(os.path.join(OUTPUT_DIR, f'concat_list_{filename_prefix}.txt'))
        with open(list_path, 'w', encoding='utf-8') as f:
            for p in audio_parts:
                escaped_p = p.replace('\\', '/')
                f.write(f"file '{escaped_p}'\n")
                
        concat_cmd = [
            FFMPEG_PATH, '-y',
            '-f', 'concat',
            '-safe', '0',
            '-i', list_path,
            '-c:a', 'libmp3lame',
            '-ar', '24000',
            '-ac', '1',
            '-b:a', '192k',
            audio_mp3
        ]
        try:
            subprocess.run(concat_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT, check=True)
        except Exception as err:
            print(f"[!] FFmpeg concat error: {err}")
            
        for p in audio_parts:
            if os.path.exists(p):
                try:
                    os.remove(p)
                except Exception:
                    pass
        if os.path.exists(list_path):
            try:
                os.remove(list_path)
            except Exception:
                pass

    if os.path.exists(audio_mp3) and os.path.getsize(audio_mp3) > 1000:
        print(f'[+] 2026 Paced Voiceover with Micro-Pauses generated ({os.path.getsize(audio_mp3)} bytes)')
        return audio_mp3, f"Documentary Baritone ({MORGAN_FREEMAN_VOICE})"
        
    return None, "None"

def generate_ai_whisper_subtitles(audio_path: str, output_ass_path: str):
    """Uses OpenAI Faster-Whisper AI model to transcribe and align subtitles with The Hormozi Effect style."""
    print('[*] Running OpenAI Whisper AI for millisecond-exact word alignment...')
    try:
        from faster_whisper import WhisperModel
        model = WhisperModel("tiny", device="cpu", compute_type="int8")
        segments, _ = model.transcribe(audio_path, word_timestamps=True)
        
        word_events = []
        for segment in segments:
            for w in segment.words:
                text_word = w.word.strip().upper()
                if text_word:
                    word_events.append({
                        'word': text_word,
                        'start': w.start,
                        'end': w.end
                    })
                    
        print(f'[+] Whisper extracted {len(word_events)} millisecond-aligned words!')
        
        bursts = []
        chunk_size = 3
        for i in range(0, len(word_events), chunk_size):
            chunk = word_events[i:i+chunk_size]
            start_t = chunk[0]['start']
            end_t = chunk[-1]['end']
            words_text = [c['word'] for c in chunk]
            bursts.append((start_t, end_t, words_text))

        ass_content = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: HormoziStyle,Montserrat,78,&H0000FFFF,&H00FFFFFF,&H00000000,&H90000000,-1,0,0,0,100,100,2,0,1,4,2,2,40,40,820,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
        for start_t, end_t, words_text in bursts:
            start_str = f"{int(start_t//3600)}:{int((start_t%3600)//60):02d}:{start_t%60:05.2f}"
            end_str = f"{int(end_t//3600)}:{int((end_t%3600)//60):02d}:{end_t%60:05.2f}"
            
            if len(words_text) > 1:
                highlighted = f"{words_text[0]} {{\\c&H00FFFFFF&}}{' '.join(words_text[1:])}"
            else:
                highlighted = f"{words_text[0]}"
                
            ass_content += f"Dialogue: 0,{start_str},{end_str},HormoziStyle,,0,0,0,,{highlighted}\n"
            
        with open(output_ass_path, "w", encoding="utf-8") as f:
            f.write(ass_content)
        print(f'[+] Created AI-Aligned Subtitles ({len(bursts)} bursts) in: {os.path.basename(output_ass_path)}')
        return True
    except Exception as e:
        print(f'[!] Whisper alignment error: {e}')
        return False

def render_2026_mastered_video(audio_path: str, raw_video_path: str, output_path: str, script_text: str, voice_info: str, prefix: str, epidemic_track_info: dict):
    """
    Renders 1M-View 2026 Mastered Documentary Short:
    1. 2026 Acoustic Room Reverb (aecho) & 3:1 Studio Compressor (compand)
    2. Speech EQ Presence Boost (3000Hz/7500Hz) & Broadcast LUFS (-14 LUFS)
    3. Epidemic Sound Music Bed Mix (-18dB)
    4. OpenAI Whisper AI Forced-Alignment Montserrat Captions
    """
    epidemic_music_file = epidemic_track_info.get('local_path') if epidemic_track_info else None
    print(f'\n[*] Rendering 2026 Mastered Documentary Short via FFmpeg...\n    Raw Input: {os.path.basename(raw_video_path)}\n    Music Track: {os.path.basename(epidemic_music_file) if epidemic_music_file else "None"}\n    Target Output: {os.path.basename(output_path)}')
    
    # 1. Calculate precise audio duration
    duration_cmd = [FFMPEG_PATH, '-i', audio_path]
    res = subprocess.run(duration_cmd, stderr=subprocess.PIPE, text=True)
    dur_match = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", res.stderr)
    if dur_match:
        hrs, mins, secs = dur_match.groups()
        audio_duration = float(hrs)*3600 + float(mins)*60 + float(secs)
    else:
        audio_duration = 30.0
        
    print(f'[+] Audio Duration: {audio_duration:.2f}s')
        
    # 2. Generate AI Whisper Subtitles
    ass_relative_filename = f'temp_subtitles_{prefix}.ass'
    ass_file = os.path.abspath(ass_relative_filename)
    generate_ai_whisper_subtitles(audio_path, ass_file)
    
    # 2026 Post-Processing Master Suite: Natural Room Presence + Studio Compressor + Warm Vocal EQ + LUFS
    reverb_comp_filter = (
        "aecho=0.8:0.85:12:0.04,"
        "compand=attacks=0.02:decays=0.25:points=-80/-80|-45/-28|-15/-10|0/-3,"
        "equalizer=f=220:t=q:w=1.2:g=1.5,equalizer=f=3200:t=q:w=1.2:g=2.0,"
        "loudnorm=I=-14:LRA=11:TP=-1.5"
    )
    
    if epidemic_music_file and os.path.exists(epidemic_music_file):
        command = [
            FFMPEG_PATH, '-y',
            '-stream_loop', '-1', '-i', raw_video_path,
            '-i', audio_path,
            '-stream_loop', '-1', '-i', epidemic_music_file,
            '-filter_complex', 
            f'[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,subtitles={ass_relative_filename}[v];'
            f'[1:a]{reverb_comp_filter}[v_a];'
            '[2:a]volume=0.12[m_a];'
            '[v_a][m_a]amix=inputs=2:duration=first:dropout_transition=2[a]',
            '-map', '[v]',
            '-map', '[a]',
            '-c:v', 'libx264',
            '-preset', 'fast',
            '-crf', '19',
            '-c:a', 'aac',
            '-b:a', '320k',
            '-t', str(audio_duration),
            output_path
        ]
    else:
        command = [
            FFMPEG_PATH, '-y',
            '-stream_loop', '-1', '-i', raw_video_path,
            '-i', audio_path,
            '-filter_complex', 
            f'[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,subtitles={ass_relative_filename}[v];'
            f'[1:a]{reverb_comp_filter}[a]',
            '-map', '[v]',
            '-map', '[a]',
            '-c:v', 'libx264',
            '-preset', 'fast',
            '-crf', '19',
            '-c:a', 'aac',
            '-b:a', '320k',
            '-t', str(audio_duration),
            output_path
        ]

    try:
        subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT, check=True)
        print(f'\n[+] SUCCESS! Rendered 2026 Mastered Short to:\n    {output_path}')
        return True
    except Exception as err:
        print(f'[!] FFmpeg render error: {err}. Running fallback render...')
        fallback_command = [
            FFMPEG_PATH, '-y',
            '-stream_loop', '-1', '-i', raw_video_path,
            '-i', audio_path,
            '-filter_complex', '[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920[v];[1:a]volume=1.0[a]',
            '-map', '[v]',
            '-map', '[a]',
            '-c:v', 'libx264',
            '-preset', 'fast',
            '-crf', '19',
            '-c:a', 'aac',
            '-t', str(audio_duration),
            output_path
        ]
        try:
            subprocess.run(fallback_command, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT, check=True)
            print(f'\n[+] SUCCESS! Rendered fallback video to:\n    {output_path}')
            return True
        except Exception as ferr:
            print(f'[!] Fallback render error: {ferr}')
            return False

def process_2026_documentary_video(raw_video_path: str, index: int):
    """Processes a raw video into a 1M-View 2026 Mastered Documentary Short."""
    filename = os.path.basename(raw_video_path)
    clean_name = os.path.splitext(filename)[0].replace('freenaturestock-', '').replace('-', ' ').title()
    prefix = f"Doc2026_Mastered_{index:02d}_{os.path.splitext(filename)[0]}"
    output_filename = f"{prefix}.mp4"
    output_path = os.path.join(OUTPUT_DIR, output_filename)
    
    print(f"\n=======================================================")
    print(f" [{index}] PROCESSING 2026 MASTERED DOCUMENTARY SHORT: {clean_name}")
    print(f"=======================================================")
    
    # 1. Generate 2026 Formatted Script
    script_data = generate_inspirational_quote_script(clean_name, quote_index=index-1)
    search_term = script_data.get('epidemic_search_term', 'epic cinematic motivation')
    
    print('\n-------------------------------------------------------')
    print(f'TITLE: {script_data.get("title")}')
    print('-------------------------------------------------------')
    print(f'2026 FORMATTED SCRIPT:\n"{script_data.get("narration_script")}"\n')
    print('-------------------------------------------------------')

    # 2. Live Epidemic Sound Track Search & Download
    epidemic_track_info = fetch_and_download_epidemic_sound_track(search_term)

    # 3. Audio Voiceover Generation
    audio_file, voice_info = generate_voiceover_audio(script_data.get('narration_script'), prefix)
    
    # 4. Video Rendering with 2026 Post-Processing Master Suite
    if audio_file:
        render_2026_mastered_video(audio_file, raw_video_path, output_path, script_data.get('narration_script'), voice_info, prefix, epidemic_track_info)
    else:
        print('[!] Audio generation failed.')

if __name__ == '__main__':
    print('--- 1M-VIEW 2026 MASTERED DOCUMENTARY SHORT AUTOMATOR ---')
    print('[*] Scanning video libraries...')
    
    videos = get_all_target_videos()
    print(f'[+] Found {len(videos)} total candidate raw videos.\n')
    
    if videos:
        # Batch process 3 shorts for the candidate videos
        batch_size = min(3, len(videos))
        print(f'[*] Starting batch generation of {batch_size} Shorts...\n')
        for i, video_path in enumerate(videos[:batch_size], 1):
            process_2026_documentary_video(video_path, i)
