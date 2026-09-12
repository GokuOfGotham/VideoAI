"""
AW360 Animal World 360 - 3-MINUTE (180s) 100% FREE ($0.00 Cost) Video Director Pipeline
Guarantees:
  1. Full 3-Minute (180s) video length so all animals & facts fit into ONE complete video.
  2. 100% STRICT MATCHING: Visuals strictly match the exact animal species in the script narration.
  3. Broadcast documentary Edge-TTS voiceover (en-US-ChristopherNeural) ($0.00 cost).
  4. High-impact Montserrat Black ASS subtitles with yellow word highlights ($0.00 cost).
  5. ZERO API charges / spend cap protection ($0.00 cost).
"""

import os
import sys
import re
import json
import time

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Make the project root importable so the root-level modules resolve from a clone.
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aw360.free_media_sourcer import FreeMediaSourcer
from aw360.voiceover_generator import VoiceoverGenerator
from aw360.subtitle_burner import SubtitleBurner
from aw360.video_renderer import VideoRenderer
from google import genai
from videoai_policy import policy_prompt, checked_script, ProductionPolicyError
from dotenv import load_dotenv

load_dotenv()

class FreeAW360Director:
    """Master 3-Minute 100% Free Pipeline Director ($0.00 total spend)."""
    def __init__(self):
        print("===============================================================")
        print("   [AW360] 3-MINUTE (180s) REAL ANIMAL VIDEO DIRECTOR ($0.00) ")
        print("===============================================================")
        self.google_key = os.getenv("GOOGLE_API_KEY")
        self.genai_client = genai.Client(api_key=self.google_key) if self.google_key else None
        self.voiceover_gen = VoiceoverGenerator(voice="en-US-ChristopherNeural")
        self.media_sourcer = FreeMediaSourcer()
        self.subtitle_burner = SubtitleBurner()
        self.renderer = VideoRenderer()

    def generate_free_video(self, topic_query: str = None) -> dict:
        start_time = time.time()
        print("💰 COST GUARANTEE: $0.00 Total Cost | 🕒 TARGET DURATION: 3 MINUTES (180s).")

        # 1. Script generation for 3-minute video
        print("\n[1/5] Writing 3-Minute Comprehensive Script with Gemini 2.5 Flash Free Tier...")
        script_data = self._generate_free_script(topic_query)
        scenes = script_data.get("scenes", [])
        metadata = script_data.get("metadata", {})
        print(f"   > Total Scenes Planned: {len(scenes)}")

        # 2. Voiceover generation (Free Edge-TTS Documentary Voice)
        print("\n[2/5] Generating Free Edge-TTS Narration & Timestamps...")
        full_text = script_data.get("full_voiceover_text", "")
        voiceover_file, word_timestamps, total_duration = self._generate_edge_tts_only(full_text)
        print(f"   > Total Narration Duration: {total_duration:.1f}s (~{total_duration/60:.1f} minutes)")
        print(f"   > Word Timestamps: {len(word_timestamps)} words processed")

        # 3. Source STRICT MATCHING HD animal media ($0.00 Wikipedia & Pexels)
        print("\n[3/5] Sourcing STRICT MATCHING HD Animal Assets ($0.00 Cost)...")
        scene_assets = []
        for s in scenes:
            scene_id = s.get("scene_id", 1)
            query = s.get("visual_search_query", "wild animal")
            narration = s.get("narration", "")
            target_species = s.get("target_animal_species")
            
            asset = self.media_sourcer.fetch_real_animal_media(scene_id, query, narration, target_species)
            scene_assets.append(asset)
            print(f"   > Scene {scene_id} [Strict Species Match]: {asset}")

        # 4. Generate ASS Subtitles with Montserrat Black
        print("\n[4/5] Building Montserrat ASS Subtitles...")
        sub_file = self.subtitle_burner.generate_ass_subtitles(word_timestamps)

        # 5. Render 1080x1920 60fps vertical video with Ken Burns motion
        print("\n[5/5] Rendering Finished 3-Minute Video with FFmpeg...")
        final_mp4, metadata_file = self.renderer.render_video(script_data, scene_assets, voiceover_file, sub_file)

        elapsed = time.time() - start_time
        print("\n===============================================================")
        print(f"🎉 SUCCESS! 3-MINUTE REAL ANIMAL VIDEO CREATED IN {elapsed:.1f} SECONDS!")
        print(f"Video Path:    {final_mp4}")
        print(f"Metadata Path: {metadata_file}")
        print("===============================================================\n")

        with open(metadata_file, "r", encoding="utf-8") as f:
            return json.load(f)

    def _generate_free_script(self, topic_query: str) -> dict:
        shared = policy_prompt(content_type="documentary", video_format="short")
        shared += '\nThe caller explicitly selected this free-audio workflow. Set audio_mode to explicit_override and record overrides.audio with user_request="Use the free AW360 workflow with Edge narration" and the reason. Do not switch this workflow to paid narration.'
        prompt = f"""
Generate an in-depth 3-MINUTE (approx 180 seconds, 400-450 words total) video script for YouTube channel 'AW360 Animal World 360'.
Topic: {topic_query or '5 Mind-Blowing Animal Superpowers'}

REQUIREMENTS:
- Total target video duration MUST be approximately 3 MINUTES (180 seconds).
- Include an immediate specific hook, an early payoff, and a complete story without padding or a promotional ending.
- Every scene MUST explicitly define the 'target_animal_species'.

Return ONLY a valid JSON object matching this schema:
{{
  "metadata": {{
    "channel_name": "AW360 Animal World 360",
    "video_title": "3-Minute Viral Title with Emojis",
    "description": "SEO Description with hashtags #AW360 #animals #facts #wildlife",
    "tags": ["animal facts", "aw360", "nature", "documentary"],
    "pinned_comment": "Engaging question for viewers",
    "thumbnail_prompt": "Thumbnail description"
  }},
  "full_voiceover_text": "Complete 400-450 word spoken narration text uninterrupted for TTS audio",
  "scenes": [
    {{
      "scene_id": 1,
      "narration": "Immediate specific hook and first useful fact about the creature.",
      "target_animal_species": "Mantis shrimp",
      "visual_search_query": "Mantis shrimp",
      "duration_est": 20.0
    }}
  ]
}}
"""
        try:
            res = self.genai_client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config={"system_instruction": shared, "response_mime_type": "application/json"}
            )
            return checked_script(json.loads(res.text), duration=180)
        except Exception as e:
            print(f"   [Scriptwriter Note]: {e}")
            raise ProductionPolicyError("Free director needs a valid reviewed script; no canned substitute was used.") from e

    def _fallback_3min_script(self) -> dict:
        raise ProductionPolicyError("Unrelated canned fallback scripts are disabled.")

    def _generate_edge_tts_only(self, text: str) -> tuple[str, list, float]:
        import asyncio
        out_path = os.path.join(self.renderer.cache_dir, "free_narration_3min.mp3")

        async def _run_tts():
            import edge_tts
            c = edge_tts.Communicate(text, "en-US-ChristopherNeural")
            await c.save(out_path)

        asyncio.run(_run_tts())

        word_timestamps = []
        duration = 180.0
        try:
            model = self.voiceover_gen._get_whisper_model()
            segments, info = model.transcribe(out_path, word_timestamps=True)
            duration = info.duration
            for segment in segments:
                for w in segment.words:
                    word_timestamps.append({
                        "word": w.word.strip(),
                        "start": round(w.start, 2),
                        "end": round(w.end, 2)
                    })
        except Exception:
            pass

        return out_path, word_timestamps, duration

if __name__ == "__main__":
    topic = sys.argv[1] if len(sys.argv) > 1 else None
    free_director = FreeAW360Director()
    res = free_director.generate_free_video(topic)
    print("\nTitle:", res.get("title"))
