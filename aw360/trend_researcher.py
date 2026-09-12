"""
AW360 Animal World 360 - Trend & Topic Researcher
Uses Google Gemini API to identify viral, high-retention animal topics and hooks.
"""

import os
import json
from dotenv import load_dotenv
from google import genai
from videoai_policy import policy_prompt, ProductionPolicyError

load_dotenv()

class TrendResearcher:
    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv("GOOGLE_API_KEY")
        if not self.api_key:
            raise ValueError("GOOGLE_API_KEY is not set in environment or provided.")
        self.client = genai.Client(api_key=self.api_key)

    def discover_trending_topic(self, user_prompt: str = None) -> dict:
        """
        Generates or selects a high-CTR, high-retention topic for AW360 Animal World 360.
        """
        system_instruction = policy_prompt(include_review=False) + "\nSuggest a topic-specific, fact-checkable concept. Distinguish researched trends from unverified ideas."


        prompt = (
            f"Generate a viral YouTube Short / video concept for AW360 Animal World 360.\n"
            f"User input/preference (if any): {user_prompt or 'Pick the most mind-blowing trending animal fact'}\n\n"
            f"Respond ONLY with a valid JSON object matching this schema:\n"
            f"{{\n"
            f'  "topic_name": "Short punchy topic name",\n'
            f'  "viral_title": "Specific, truthful title (max 60 chars, emojis allowed)",\n'
            f'  "hook": "The opening 3-second hook line that stops scrolling instantly",\n'
            f'  "target_emotion": "shock | awe | fear | fascination | humor",\n'
            f'  "concept_summary": "Brief 2-sentence summary of why this topic could interest viewers",\n'
            f'  "thumbnail_concept": "Visual description for a viral thumbnail (e.g. glowing eyes in dark ocean)"\n'
            f"}}\n"
        )

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
            raise ProductionPolicyError("Topic generation failed; no unrelated topic was substituted.") from e

if __name__ == "__main__":
    researcher = TrendResearcher()
    topic = researcher.discover_trending_topic()
    print("Discovered Topic:")
    print(json.dumps(topic, indent=2))
