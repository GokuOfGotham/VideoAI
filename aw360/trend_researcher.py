"""
AW360 Animal World 360 - Trend & Topic Researcher
Uses Google Gemini API to identify viral, high-retention animal topics and hooks.
"""

import os
import json
from dotenv import load_dotenv
from google import genai

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
        system_instruction = (
            "You are the Lead Creative Director for AW360 Animal World 360, a top-tier YouTube channel "
            "specializing in viral animal facts, mind-bending biology, and epic wildlife stories. "
            "Your goal is to engineer videos that achieve 1M+ views by creating un-skippable hooks, "
            "intense curiosity gaps, and fascinating, verified animal facts."
        )

        prompt = (
            f"Generate a viral YouTube Short / video concept for AW360 Animal World 360.\n"
            f"User input/preference (if any): {user_prompt or 'Pick the most mind-blowing trending animal fact'}\n\n"
            f"Respond ONLY with a valid JSON object matching this schema:\n"
            f"{{\n"
            f'  "topic_name": "Short punchy topic name",\n'
            f'  "viral_title": "1M-view CTR Title (max 60 chars, emojis allowed)",\n'
            f'  "hook": "The opening 3-second hook line that stops scrolling instantly",\n'
            f'  "target_emotion": "shock | awe | fear | fascination | humor",\n'
            f'  "concept_summary": "Brief 2-sentence summary of why this video will go viral",\n'
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
            # Fallback if json parsing fails
            return {
                "topic_name": "Secret Superpowers of Everyday Animals",
                "viral_title": "Animals with REAL Superpowers You Won't Believe! 😱",
                "hook": "Did you know there is a shrimp that punches with the speed of a bullet?",
                "target_emotion": "shock",
                "concept_summary": "Revealing hidden biological superpowers of familiar animals.",
                "thumbnail_concept": "Mantis shrimp with glowing hyper-energy punch effect underwater."
            }

if __name__ == "__main__":
    researcher = TrendResearcher()
    topic = researcher.discover_trending_topic()
    print("Discovered Topic:")
    print(json.dumps(topic, indent=2))
