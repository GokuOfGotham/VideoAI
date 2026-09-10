"""Voice Synthesizer for VideoAI.

Ultra High-Def Studio Vocal Mastering Edition:
- Local Voicebox GPU Engine integration (NVIDIA RTX 5070, James Earl Jones profile).
- 7-Band Precision Vocal Equalizer:
  - 85Hz Highpass Rumble Cut
  - 160Hz Proximity Radio Warmth (+2.5dB)
  - 280Hz & 450Hz Room Acoustic Boxiness & Echo Notch (-7dB / -5dB)
  - 2.5kHz Intelligibility Boost (+3dB)
  - 4.2kHz HD Presence (+5.5dB)
  - 10kHz Condenser Air & Polish (+3.5dB)
- Studio Vocal De-Esser (`deesser=i=0.5:m=0.5:f=0.5`) to eliminate harsh sibilance.
- Studio Opto-Compressor (`compand`) & EBU R128 (-16 LUFS) Broadcast Loudness Normalization.
"""

import asyncio
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import requests
from dotenv import load_dotenv

from script_normalizer import normalize_script_for_tts, chunk_script_text

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent
ASSETS_DIR = PROJECT_ROOT / "assets"
os.makedirs(ASSETS_DIR, exist_ok=True)

VOICEBOX_URL = os.getenv("VOICEBOX_URL", "http://127.0.0.1:17493").rstrip("/")
DEFAULT_EDGE_VOICE = "en-US-GuyNeural"

# Edge voice ids look like "en-US-GuyNeural" / "zh-CN-XiaoxiaoNeural".
_EDGE_VOICE_PATTERN = re.compile(r"^[a-z]{2,3}(?:-[A-Za-z]{2,8})?-[A-Z]{2}-\w+Neural$")

# Voicebox profiles are cloned-voice names, not Edge ids. When Voicebox is
# unreachable the profile name cannot be handed to Edge-TTS, which rejects
# anything that is not one of its own ids, so map the profiles this project
# ships to their nearest Edge equivalent.
_VOICEBOX_TO_EDGE = {
    "james earl jones": "en-US-GuyNeural",
    "morgan freeman": "en-US-GuyNeural",
    "christopher": "en-US-ChristopherNeural",
    "david attenborough": "en-GB-RyanNeural",
}

# Master Audio Director Presets for ElevenLabs
ELEVENLABS_STABILITY = 0.70
ELEVENLABS_SIMILARITY_BOOST = 0.82
ELEVENLABS_STYLE_EXAGGERATION = 0.25


def synthesize_narration(
    text: str,
    output_filename: str = "narration.mp3",
    provider: str = "voicebox",
    voice: str = "James Earl Jones",
    pitch: str = "+0Hz",
    rate: str = "+0%"
) -> Tuple[str, float, List[Dict]]:
    """Synthesizes voiceover audio using local Voicebox (James Earl Jones) or fallback TTS with Ultra HD Mastering."""
    audio_path = str(ASSETS_DIR / output_filename)

    # 1. Master Script Normalization
    normalized_text = normalize_script_for_tts(text)

    # 2. Chunking script (max 650 chars) to prevent emotional drift & pacing decay
    chunks = chunk_script_text(normalized_text, max_chars=650)

    if len(chunks) == 1:
        _synthesize_single_chunk(chunks[0], audio_path, provider, voice, pitch, rate)
    else:
        chunk_files = []
        for i, ch_text in enumerate(chunks):
            ch_path = str(ASSETS_DIR / f"chunk_{i}_{output_filename}")
            _synthesize_single_chunk(ch_text, ch_path, provider, voice, pitch, rate)
            chunk_files.append(ch_path)

        _concat_audio_chunks(chunk_files, audio_path)

    # 3. Apply Ultra High-Def Studio Vocal Mastering (7-band EQ + De-esser + Opto-Compressor + LUFS Normalization)
    _apply_studio_vocal_mastering(audio_path)

    duration = get_audio_duration(audio_path)
    timestamps = _extract_word_timestamps(audio_path, normalized_text)

    return audio_path, duration, timestamps


def _apply_studio_vocal_mastering(audio_path: str):
    """Applies FFmpeg Ultra High-Def Studio Vocal Mastering Filter Chain."""
    temp_mastered = audio_path + ".ultrahd.mp3"
    filter_chain = (
        "highpass=f=85,"
        "equalizer=f=160:width_type=h:width=100:g=2.5,"
        "equalizer=f=280:width_type=h:width=150:g=-7,"
        "equalizer=f=450:width_type=h:width=200:g=-5,"
        "equalizer=f=2500:width_type=h:width=800:g=3,"
        "equalizer=f=4200:width_type=h:width=1200:g=5.5,"
        "equalizer=f=10000:width_type=h:width=3000:g=3.5,"
        "deesser=i=0.5:m=0.5:f=0.5,"
        "compand=attacks=0.01:decays=0.1:points=-60/-60|-24/-12|-8/-3|0/0:gain=3,"
        "loudnorm=I=-16:LRA=7:TP=-1.5"
    )
    cmd = ["ffmpeg", "-y", "-i", audio_path, "-af", filter_chain, "-ar", "48000", "-b:a", "320k", temp_mastered]
    try:
        subprocess.run(cmd, capture_output=True, check=True)
        if os.path.exists(temp_mastered) and os.path.getsize(temp_mastered) > 0:
            os.replace(temp_mastered, audio_path)
            print(f"[VoiceSynthesizer] Applied Ultra High-Def Studio Vocal Mastering (7-Band EQ + De-Esser + Compressor + -16 LUFS).")
    except Exception as e:
        print(f"[VoiceSynthesizer] Ultra HD audio mastering warning: {e}")


def _synthesize_single_chunk(text: str, output_path: str, provider: str, voice: str, pitch: str, rate: str):
    """Synthesizes a single chunk using chosen TTS provider with graceful fallback."""
    if provider == "voicebox":
        try:
            _synthesize_voicebox_tts(text, output_path, voice_name=voice)
            return
        except Exception as e:
            print(f"[VoiceSynthesizer] Voicebox TTS failed ({e}). Falling back to Edge-TTS.")

    if provider == "elevenlabs":
        _synthesize_elevenlabs_tts(text, output_path, voice_id=voice)
    elif provider == "openai":
        try:
            _synthesize_openai_tts(text, output_path, voice="onyx")
        except Exception as e:
            print(f"[VoiceSynthesizer] OpenAI TTS failed ({e}). Falling back to Edge-TTS {DEFAULT_EDGE_VOICE}.")
            _synthesize_edge_tts(text, output_path, voice=DEFAULT_EDGE_VOICE, pitch="+0Hz", rate="+0%")
    else:
        _synthesize_edge_tts(text, output_path, voice=_resolve_edge_voice(voice), pitch=pitch, rate=rate)


def _resolve_edge_voice(voice: str) -> str:
    """Maps whatever voice the caller asked for onto a valid Edge-TTS id.

    The Voicebox fallback path arrives here still carrying a Voicebox profile
    name, and Edge-TTS raises on anything that is not one of its own ids, so an
    unrecognised name has to degrade to the default rather than be passed on.
    """
    candidate = (voice or "").strip()
    if _EDGE_VOICE_PATTERN.match(candidate):
        return candidate

    mapped = _VOICEBOX_TO_EDGE.get(candidate.lower())
    if mapped:
        print(f"[VoiceSynthesizer] '{candidate}' is a Voicebox profile; using Edge voice {mapped}.")
        return mapped

    if candidate:
        print(
            f"[VoiceSynthesizer] '{candidate}' is not an Edge voice id; "
            f"using {DEFAULT_EDGE_VOICE}."
        )
    return DEFAULT_EDGE_VOICE


def _synthesize_voicebox_tts(text: str, output_path: str, voice_name: str = "James Earl Jones"):
    """Synthesizes speech using local Voicebox server (GPU accelerated) with cloned voice profile."""
    resp = requests.get(f"{VOICEBOX_URL}/profiles", timeout=10)
    resp.raise_for_status()
    profiles = resp.json()

    if not profiles:
        raise RuntimeError("No voice profiles found on local Voicebox server.")

    target_profile = None
    for p in profiles:
        if voice_name.lower() in p.get("name", "").lower():
            target_profile = p
            break

    if not target_profile:
        target_profile = profiles[0]

    profile_id = target_profile["id"]
    print(f"[Voicebox] Using local voice profile '{target_profile.get('name')}' ({profile_id})")

    gen_resp = requests.post(
        f"{VOICEBOX_URL}/generate",
        json={"profile_id": profile_id, "text": text, "engine": "qwen"},
        timeout=15
    )
    gen_resp.raise_for_status()
    gen_data = gen_resp.json()
    gen_id = gen_data["id"]

    start_time = time.time()
    while time.time() - start_time < 90:
        time.sleep(1.5)
        st_resp = requests.get(f"{VOICEBOX_URL}/generate/{gen_id}/status", timeout=10)
        if st_resp.status_code != 200:
            continue

        try:
            st_data = st_resp.json()
            status = st_data.get("status")
            if status == "completed":
                break
            elif status == "failed":
                raise RuntimeError(f"Voicebox generation failed: {st_data.get('error')}")
        except Exception:
            continue

    audio_resp = requests.get(f"{VOICEBOX_URL}/audio/{gen_id}", timeout=30)
    audio_resp.raise_for_status()

    with open(output_path, "wb") as f:
        f.write(audio_resp.content)

    print(f"[Voicebox] Audio downloaded successfully to {output_path}")


def _synthesize_edge_tts(text: str, output_path: str, voice: str, pitch: str, rate: str):
    """Synthesizes text using edge-tts async runner with natural pitch/rate."""
    async def _async_gen():
        import edge_tts
        v = voice if voice and voice not in ("edge", "voicebox") else DEFAULT_EDGE_VOICE
        communicate = edge_tts.Communicate(text, v, pitch=pitch, rate=rate)
        await communicate.save(output_path)

    asyncio.run(_async_gen())


def _synthesize_elevenlabs_tts(text: str, output_path: str, voice_id: str = "21m00Tcm4TlvDq8ikWAM"):
    """Synthesizes text using ElevenLabs API with strict Voiceover Director parameters."""
    api_key = os.getenv("ELEVENLABS_API_KEY")
    if not api_key:
        print("[VoiceSynthesizer] ELEVENLABS_API_KEY missing, falling back to Edge-TTS.")
        _synthesize_edge_tts(text, output_path, DEFAULT_EDGE_VOICE, "+0Hz", "+0%")
        return

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    headers = {
        "xi-api-key": api_key,
        "Content-Type": "application/json"
    }
    payload = {
        "text": text,
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {
            "stability": ELEVENLABS_STABILITY,
            "similarity_boost": ELEVENLABS_SIMILARITY_BOOST,
            "style": ELEVENLABS_STYLE_EXAGGERATION,
            "use_speaker_boost": True
        }
    }

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=35)
        resp.raise_for_status()
        with open(output_path, "wb") as f:
            f.write(resp.content)
    except Exception as e:
        print(f"[VoiceSynthesizer] ElevenLabs TTS failed ({e}). Falling back to Edge-TTS.")
        _synthesize_edge_tts(text, output_path, DEFAULT_EDGE_VOICE, "+0Hz", "+0%")


def _synthesize_openai_tts(text: str, output_path: str, voice: str = "onyx"):
    """Synthesizes text using OpenAI TTS API."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY is required for OpenAI TTS.")

    url = "https://api.openai.com/v1/audio/speech"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "tts-1-hd",
        "input": text,
        "voice": voice,
        "response_format": "mp3"
    }

    resp = requests.post(url, headers=headers, json=payload, timeout=30)
    resp.raise_for_status()
    with open(output_path, "wb") as f:
        f.write(resp.content)


def _concat_audio_chunks(chunk_paths: List[str], output_path: str):
    """Concatenates multiple audio files into a single seamless audio track using FFmpeg."""
    list_file = str(ASSETS_DIR / "concat_chunks.txt")
    with open(list_file, "w", encoding="utf-8") as f:
        for p in chunk_paths:
            f.write(f"file '{p.replace('\\', '/')}'\n")

    cmd = [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", list_file, "-c", "copy", output_path
    ]
    subprocess.run(cmd, capture_output=True, check=True)


def get_audio_duration(audio_path: str) -> float:
    """Gets audio duration in seconds using ffprobe."""
    cmd = [
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", audio_path
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return float(res.stdout.strip())
    except Exception:
        return 10.0


def _extract_word_timestamps(audio_path: str, full_text: str) -> List[Dict]:
    """Uses Faster-Whisper to extract word-level timestamps or falls back to word length estimation."""
    try:
        from faster_whisper import WhisperModel
        model = WhisperModel("base", device="cpu", compute_type="int8")
        segments, _ = model.transcribe(audio_path, word_timestamps=True)

        words_list = []
        for segment in segments:
            for word_info in segment.words:
                words_list.append({
                    "word": word_info.word.strip(),
                    "start": round(word_info.start, 2),
                    "end": round(word_info.end, 2)
                })

        if words_list:
            return words_list

    except Exception as e:
        print(f"[VoiceSynthesizer] Whisper fallback ({e}). Estimating word timestamps.")

    words = full_text.split()
    total_chars = sum(len(w) for w in words)
    duration = get_audio_duration(audio_path)

    timestamps = []
    current_time = 0.0
    for w in words:
        w_dur = max(0.2, round((len(w) / max(1, total_chars)) * duration, 2))
        timestamps.append({
            "word": w,
            "start": round(current_time, 2),
            "end": round(current_time + w_dur, 2)
        })
        current_time += w_dur

    return timestamps


if __name__ == "__main__":
    test_text = "In the 1990s, AWS cost $45.67! Furthermore, SQLite is fast in 2026."
    path, dur, words = synthesize_narration(test_text, provider="voicebox")
    print(f"Voicebox James Earl Jones Synthesized & Ultra HD Mastered: {path} ({dur}s), words={len(words)}")
