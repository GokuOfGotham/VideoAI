"""
AW360 Animal World 360 - Premium Voiceover Generator
Generates high-definition voiceover narration using OpenAI TTS (Onyx/Echo) or Edge TTS (Christopher),
and aligns word-level timestamps using Faster-Whisper.
"""

import os
import asyncio
import subprocess
import requests
from dotenv import load_dotenv
import edge_tts
from faster_whisper import WhisperModel

from . import paths

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

class VoiceoverGenerator:
    def __init__(self, voice: str = "en-US-ChristopherNeural", cache_dir: str = None):
        self.voice = voice
        self.cache_dir = str(cache_dir or paths.CACHE_DIR)
        os.makedirs(self.cache_dir, exist_ok=True)
        self._whisper_model = None

    def _get_whisper_model(self):
        if self._whisper_model is None:
            self._whisper_model = WhisperModel("tiny.en", device="cpu", compute_type="int8")
        return self._whisper_model

    def generate_narration(self, text: str, output_path: str = None) -> tuple[str, list, float]:
        """
        Generates broadcast quality narration audio file.
        Returns (audio_file_path, word_timestamps_list, duration_seconds).
        """
        if not output_path:
            output_path = os.path.join(self.cache_dir, "narration_full.mp3")

        # 1. Prefer OpenAI HD TTS voice if OPENAI_API_KEY is available
        generated = False
        if OPENAI_API_KEY:
            print("   [VoiceoverGenerator] Generating OpenAI HD Documentary Voiceover (Voice: Onyx)...")
            generated = self._create_openai_tts(text, output_path, voice="onyx")

        # 2. Fallback to Edge TTS
        if not generated:
            print(f"   [VoiceoverGenerator] Generating Edge TTS Voiceover ({self.voice})...")
            asyncio.run(self._create_edge_tts(text, output_path))

        # 3. Extract word level timestamps using Faster Whisper
        word_timestamps = []
        duration = 0.0
        try:
            model = self._get_whisper_model()
            segments, info = model.transcribe(output_path, word_timestamps=True)
            duration = info.duration
            for segment in segments:
                for w in segment.words:
                    word_timestamps.append({
                        "word": w.word.strip(),
                        "start": round(w.start, 2),
                        "end": round(w.end, 2)
                    })
        except Exception as e:
            print(f"   [VoiceoverGenerator] Faster-Whisper note: {e}")
            duration = self._get_audio_duration(output_path)

        return output_path, word_timestamps, duration

    def _create_openai_tts(self, text: str, dest_path: str, voice: str = "onyx") -> bool:
        """Generates TTS audio via OpenAI Audio API."""
        try:
            url = "https://api.openai.com/v1/audio/speech"
            headers = {
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": "tts-1-hd",
                "input": text,
                "voice": voice,
                "speed": 1.05
            }
            r = requests.post(url, headers=headers, json=payload, timeout=30)
            if r.status_code == 200:
                with open(dest_path, "wb") as f:
                    f.write(r.content)
                return True
            else:
                print(f"   [VoiceoverGenerator] OpenAI TTS error {r.status_code}: {r.text}")
        except Exception as e:
            print(f"   [VoiceoverGenerator] OpenAI TTS exception: {e}")
        return False

    async def _create_edge_tts(self, text: str, dest_path: str):
        communicate = edge_tts.Communicate(text, self.voice)
        await communicate.save(dest_path)

    def _get_audio_duration(self, audio_path: str) -> float:
        try:
            cmd = [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                audio_path
            ]
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
            return float(res.stdout.strip())
        except Exception:
            return 30.0

if __name__ == "__main__":
    vg = VoiceoverGenerator()
    audio, words, dur = vg.generate_narration("Welcome to AW360 Animal World 360!")
    print(f"Generated Audio: {audio} | Duration: {dur}s | Words: {len(words)}")
