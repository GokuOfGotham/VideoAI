"""Script and Scene Generator for VideoAI.

Uses LLM APIs (OpenAI, Gemini, DeepSeek) to turn a topic or prompt into a
structured script with narration, scene timing, and visual search terms.
"""

import json
import os
import re
from typing import Any, Dict, List, Optional
import requests
from dotenv import load_dotenv

load_dotenv()


def generate_video_script(
    topic: str,
    target_duration_seconds: int = 30,
    llm_provider: str = "openai",
    model_name: Optional[str] = None
) -> Dict[str, Any]:
    """Generates a structured video script JSON from a topic.

    Returns dict with keys:
        - title: str
        - narration_script: str
        - epidemic_search_term: str
        - scenes: List[Dict] with 'scene_text', 'search_keywords', 'duration_est'
    """
    prompt = f"""
You are an expert short-form viral video director and scriptwriter (TikTok, Shorts, Reels).
Generate a high-retention script for a {target_duration_seconds}-second vertical video about: "{topic}".

Rules:
1. Tone: Engaging, punchy, dramatic pacing, no generic AI filler.
2. Narration: Written for text-to-speech. Spell out numbers as words ("twenty twenty-six").
3. Split the narration into 3 to 6 distinct visual scenes.
4. Provide visual search keywords for each scene suitable for military/stock footage searching.

Respond ONLY with valid JSON in this exact structure:
{{
    "title": "Short Descriptive Title",
    "narration_script": "Complete narration monologue text here...",
    "epidemic_search_term": "ambient cinematic tension",
    "scenes": [
        {{
            "scene_id": 1,
            "scene_text": "First sentence of narration...",
            "search_keywords": "military stealth fighter missile defense radar",
            "duration_est": 5.0
        }}
    ]
}}
"""

    api_key = os.getenv("OPENAI_API_KEY")
    google_key = os.getenv("GOOGLE_API_KEY")
    deepseek_key = os.getenv("DEEPSEEK_API_KEY")

    if (llm_provider == "gemini" or google_key) and not (llm_provider == "openai" and api_key):
        res = _call_gemini_chat(prompt, model_name or "gemini-2.5-flash", google_key, topic, target_duration_seconds)
        if res:
            return res

    if api_key:
        res = _call_openai_chat(prompt, model_name or "gpt-4o-mini", api_key, topic, target_duration_seconds)
        if res:
            return res

    if deepseek_key:
        res = _call_openai_compatible(
            prompt,
            model_name or "deepseek-chat",
            deepseek_key,
            "https://api.deepseek.com/v1",
            topic,
            target_duration_seconds
        )
        if res:
            return res

    return _fallback_template_script(topic, target_duration_seconds)


def _call_openai_chat(prompt: str, model: str, api_key: Optional[str], topic: str, duration: int) -> Optional[Dict[str, Any]]:
    if not api_key:
        return None

    url = "https://api.openai.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": model,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": "You are a professional video script assistant. Output JSON only."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.7
    }

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        return json.loads(content)
    except Exception as e:
        print(f"[ScriptGenerator] OpenAI call failed ({e}). Trying fallback.")
        return None


def _call_gemini_chat(prompt: str, model: str, api_key: Optional[str], topic: str, duration: int) -> Optional[Dict[str, Any]]:
    if not api_key:
        return None

    # Try gemini-2.5-flash first, fallback to gemini-1.5-flash-latest
    for m in [model, "gemini-2.5-flash", "gemini-1.5-flash-latest", "gemini-1.5-pro"]:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent?key={api_key}"
        headers = {"Content-Type": "application/json"}
        payload = {
            "contents": [{"parts": [{"text": prompt + "\nRespond strictly in valid JSON."}]}],
            "generationConfig": {"responseMimeType": "application/json"}
        }

        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=25)
            if resp.status_code == 200:
                raw_text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
                return json.loads(raw_text)
        except Exception:
            continue

    print(f"[ScriptGenerator] Gemini endpoints exhausted. Using fallback script.")
    return None


def _call_openai_compatible(prompt: str, model: str, api_key: Optional[str], base_url: str, topic: str, duration: int) -> Optional[Dict[str, Any]]:
    if not api_key:
        return None

    url = f"{base_url.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are a professional video script assistant. Output JSON only."},
            {"role": "user", "content": prompt}
        ]
    }

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        cleaned = re.sub(r"^```json\s*|\s*```$", "", content.strip(), flags=re.MULTILINE)
        return json.loads(cleaned)
    except Exception as e:
        print(f"[ScriptGenerator] LLM call failed ({e}).")
        return None


def _fallback_template_script(topic: str, duration: int) -> Dict[str, Any]:
    """Generates a contextual fallback script structure matching the requested topic."""
    is_military = any(k in topic.lower() for k in ["ukraine", "russia", "military", "war", "drone", "tactical", "combat", "navy"])

    if is_military:
        return {
            "title": f"Ukraine vs Russia: Modern Tactical Shift",
            "narration_script": (
                "Modern warfare is shifting at unprecedented speed. [pause 1.0s] "
                "Autonomous drone swarms and high precision electronic warfare have rewritten the frontline rules. "
                "Success no longer depends solely on heavy armor—it's driven by speed, real-time intelligence, and relentless tactical adaptation."
            ),
            "epidemic_search_term": "epic hybrid orchestral trailer action",
            "scenes": [
                {
                    "scene_id": 1,
                    "scene_text": "Modern warfare is shifting at unprecedented speed.",
                    "search_keywords": "military fighter jet launch kinetic radar",
                    "duration_est": 6.0
                },
                {
                    "scene_id": 2,
                    "scene_text": "Autonomous drone swarms and high precision electronic warfare have rewritten the frontline rules.",
                    "search_keywords": "stealth bomber dark sky military flight operations",
                    "duration_est": 8.0
                },
                {
                    "scene_id": 3,
                    "scene_text": "Success no longer depends solely on heavy armor—it's driven by speed, real-time intelligence, and relentless tactical adaptation.",
                    "search_keywords": "aircraft carrier military night flight supersonic",
                    "duration_est": 8.0
                }
            ]
        }

    return {
        "title": f"The Reality of {topic.title()}",
        "narration_script": (
            f"Most people underestimate the reality of {topic}. [pause 1.0s] "
            "Real discipline is silent. It is the raw friction of execution every single day. "
            "Push past the resistance and dominate your path."
        ),
        "epidemic_search_term": "intense cinematic dark motivation",
        "scenes": [
            {
                "scene_id": 1,
                "scene_text": f"Most people underestimate the reality of {topic}.",
                "search_keywords": f"{topic} dramatic cinematic",
                "duration_est": 5.0
            },
            {
                "scene_id": 2,
                "scene_text": "Real discipline is silent. It is the raw friction of execution every single day.",
                "search_keywords": "athlete workout rain dark night",
                "duration_est": 7.0
            },
            {
                "scene_id": 3,
                "scene_text": "Push past the resistance and dominate your path.",
                "search_keywords": "epic sunset mountain horizon",
                "duration_est": 6.0
            }
        ]
    }


if __name__ == "__main__":
    script = generate_video_script("Ukraine vs Russia", target_duration_seconds=20)
    print(json.dumps(script, indent=2))
