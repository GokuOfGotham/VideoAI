"""
AW360 Animal World 360 - Director Scriptwriter
Uses Google Gemini API to generate structured 1M-view video director scripts.
"""

import os
import json
from dotenv import load_dotenv
from google import genai
from videoai_policy import policy_prompt, checked_script, ProductionPolicyError

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
        system_instruction = policy_prompt(content_type="documentary", video_format="short")


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
    "video_title": "Specific, truthful title matching the opening",
    "description": "SEO Description with 4-5 relevant hashtags",
    "tags": ["tag1", "tag2", "tag3", "tag4", "tag5"],
    "pinned_comment": "Optional relevant discussion question",
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
            return checked_script(data, duration=60)
        except Exception as e:
            print(f"[Scriptwriter] Error parsing JSON response: {e}")
            # Clean fallback
            raise ProductionPolicyError("Director script is invalid; repair it before production.") from e

    def _get_fallback_script(self, topic_info: dict) -> dict:
        raise ProductionPolicyError("Unrelated canned fallback scripts are disabled.")
