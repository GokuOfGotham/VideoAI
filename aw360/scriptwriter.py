"""
AW360 Animal World 360 - Director Scriptwriter
Uses Google Gemini API to generate structured 1M-view video director scripts.
"""

import os
import json
from dotenv import load_dotenv
from google import genai

load_dotenv()

class DirectorScriptwriter:
    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv("GOOGLE_API_KEY")
        if not self.api_key:
            raise ValueError("GOOGLE_API_KEY is not set in environment or provided.")
        self.client = genai.Client(api_key=self.api_key)

    def generate_script(self, topic_info: dict) -> dict:
        """
        Generates a complete production script with scene-by-scene timing,
        stock video search queries, AI image prompts, narration, and metadata.
        """
        system_instruction = (
            "You are an elite YouTube Video Director & Master Scriptwriter for AW360 Animal World 360. "
            "Your scripts are engineered for 90%+ retention on YouTube Shorts and TikTok. "
            "You use psychological hooks, rapid pacing, vivid descriptions, and clear call-to-actions."
        )

        prompt = f"""
Generate a complete, production-ready video script for YouTube Channel 'AW360 Animal World 360'.

Topic Details:
- Name: {topic_info.get('topic_name')}
- Suggested Title: {topic_info.get('viral_title')}
- Target Emotion: {topic_info.get('target_emotion', 'awe')}
- Hook: {topic_info.get('hook')}

Target Duration: ~45-60 seconds (approx 120-150 spoken words total across 5-7 visual scenes).

IMPORTANT FORMAT REQUIREMENTS:
Return ONLY a valid JSON object matching this exact JSON schema:
{{
  "metadata": {{
    "channel_name": "AW360 Animal World 360",
    "video_title": "Viral 1M-view Title with Emojis",
    "description": "SEO Description with 4-5 relevant hashtags",
    "tags": ["tag1", "tag2", "tag3", "tag4", "tag5"],
    "pinned_comment": "Engaging question to force viewers to comment",
    "music_mood": "epic | suspenseful | energetic | dark | awe",
    "thumbnail_prompt": "Detailed AI prompt for creating the video thumbnail"
  }},
  "full_voiceover_text": "Complete spoken text uninterrupted for TTS audio generation",
  "scenes": [
    {{
      "scene_id": 1,
      "narration": "First 3-5 seconds hook spoken line.",
      "visual_search_query": "specific search terms for stock footage e.g. mantis shrimp punch slow motion",
      "ai_image_prompt": "Ultra realistic 8k photo of mantis shrimp under glowing ocean water, dramatic lighting, 9:16 vertical",
      "motion": "zoom_in | zoom_out | pan_right | pan_left",
      "duration_est": 7.0
    }}
  ]
}}
"""

        response = self.client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config={
                "system_instruction": system_instruction,
                "response_mime_type": "application/json"
            }
        )

        try:
            data = json.loads(response.text)
            return data
        except Exception as e:
            print(f"[Scriptwriter] Error parsing JSON response: {e}")
            # Clean fallback
            return self._get_fallback_script(topic_info)

    def _get_fallback_script(self, topic_info: dict) -> dict:
        return {
            "metadata": {
                "channel_name": "AW360 Animal World 360",
                "video_title": "Animals With REAL Superpowers! 😱 #AW360",
                "description": "Discover the most insane biological superpowers in the animal kingdom! Subscribe to AW360 Animal World 360 for daily wild facts! #animals #facts #nature #aw360 #wildlife",
                "tags": ["animal facts", "aw360", "animal world 360", "superpowers", "wildlife", "shorts"],
                "pinned_comment": "Which animal superpower would you want? Tell us below! 👇",
                "music_mood": "epic",
                "thumbnail_prompt": "Hyperrealistic close up of a mantis shrimp underwater striking with glowing energy, photorealistic 8k"
            },
            "full_voiceover_text": "Did you know there is a tiny sea creature that punches with the force of a bullet? Meet the Mantis Shrimp. Its claws accelerate faster than a 22 caliber bullet, striking so fast the surrounding water boils! Next up: the immortal jellyfish. When old or injured, it can reset its cells back to a baby polyp, living forever. And the archerfish shoots precise water jets 6 feet in the air to knock insects right into its mouth! Subscribe to AW360 Animal World 360 for more mind blowing animal facts!",
            "scenes": [
                {
                    "scene_id": 1,
                    "narration": "Did you know there is a tiny sea creature that punches with the force of a bullet?",
                    "visual_search_query": "mantis shrimp underwater ocean",
                    "ai_image_prompt": "Close up of colourful mantis shrimp underwater in tropical ocean reef, 8k vertical",
                    "motion": "zoom_in",
                    "duration_est": 6.0
                },
                {
                    "scene_id": 2,
                    "narration": "Meet the Mantis Shrimp. Its claws accelerate faster than a 22 caliber bullet, striking so fast the water boils!",
                    "visual_search_query": "mantis shrimp striking underwater",
                    "ai_image_prompt": "Mantis shrimp underwater releasing high speed shockwave punch, glowing water bubble, 8k vertical",
                    "motion": "zoom_out",
                    "duration_est": 8.0
                },
                {
                    "scene_id": 3,
                    "narration": "Next up: the immortal jellyfish. When old or injured, it can reset its cells back to a baby polyp, living forever.",
                    "visual_search_query": "glowing jellyfish deep ocean blue water",
                    "ai_image_prompt": "Bioluminescent glowing jellyfish floating in deep dark ocean water, cinematic lighting, 8k vertical",
                    "motion": "pan_right",
                    "duration_est": 8.0
                },
                {
                    "scene_id": 4,
                    "narration": "And the archerfish shoots precise water jets 6 feet in the air to knock insects right into its mouth!",
                    "visual_search_query": "archerfish spitting water insect mangrove",
                    "ai_image_prompt": "Archerfish underwater shooting water jet towards insect on branch above water, high speed photography, 8k vertical",
                    "motion": "zoom_in",
                    "duration_est": 7.0
                },
                {
                    "scene_id": 5,
                    "narration": "Subscribe to AW360 Animal World 360 for more mind blowing animal facts!",
                    "visual_search_query": "wild majestic eagle soaring sky nature",
                    "ai_image_prompt": "Majestic golden eagle flying high above breathtaking mountain landscape at sunset, 8k vertical",
                    "motion": "zoom_out",
                    "duration_est": 5.0
                }
            ]
        }

if __name__ == "__main__":
    writer = DirectorScriptwriter()
    topic = {"topic_name": "Deadliest Animals", "viral_title": "5 Animals That Could End You", "hook": "You won't believe #1"}
    script = writer.generate_script(topic)
    print("Generated Script:")
    print(json.dumps(script, indent=2))
