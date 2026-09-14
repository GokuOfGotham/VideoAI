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
from videoai_policy import policy_prompt, checked_script, ProductionPolicyError

load_dotenv()


def generate_video_script(topic: str, target_duration_seconds: int = 30,
                          llm_provider: str = "openai", model_name: Optional[str] = None,
                          content_type: str = "documentary", video_format: str = "short") -> Dict[str, Any]:
    """Every provider receives the same policy; invalid/fallback scripts stop production."""
    if llm_provider not in {"openai", "gemini", "deepseek"}:
        raise ValueError("Unsupported provider; use the shared policy adapter for new providers.")
    if target_duration_seconds <= 0:
        raise ValueError("target_duration_seconds must be positive")
    frame = "vertical" if video_format == "short" else "wide"
    prompt = policy_prompt(content_type=content_type, video_format=video_format)
    prompt += f"\nWrite a {target_duration_seconds}-second {frame} video about {topic!r}. "
    prompt += "Use topic-specific visual search terms. Use enough scenes for the actual story, with estimated timings totaling the requested runtime. Spell numbers naturally for speech. Return JSON only with title, narration_script, epidemic_search_term, scenes and production_review. Each scene needs scene_id, scene_text, search_keywords, duration_est and editorial purpose."
    order = [llm_provider] + [p for p in ["openai", "gemini", "deepseek"] if p != llm_provider]
    for provider in order:
        selected_model = model_name if provider == llm_provider else None
        if provider == "openai":
            data = _call_openai_chat(prompt, selected_model or "gpt-4o-mini", os.getenv("OPENAI_API_KEY"), topic, target_duration_seconds)
        elif provider == "gemini":
            data = _call_gemini_chat(prompt, selected_model or "gemini-2.5-flash", os.getenv("GOOGLE_API_KEY"), topic, target_duration_seconds)
        else:
            data = _call_openai_compatible(prompt, selected_model or "deepseek-chat", os.getenv("DEEPSEEK_API_KEY"), "https://api.deepseek.com/v1", topic, target_duration_seconds)
        if data is not None:
            return checked_script(data, duration=target_duration_seconds)
    raise ProductionPolicyError("No provider returned a usable script. No canned replacement was produced; fix the provider or supply a reviewed script.")

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
            {"role": "system", "content": policy_prompt(include_review=False) + "\nYou are a professional video script assistant. Output JSON only."},
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
            "systemInstruction": {"parts": [{"text": policy_prompt(include_review=False)}]},
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
            {"role": "system", "content": policy_prompt(include_review=False) + "\nYou are a professional video script assistant. Output JSON only."},
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
    raise ProductionPolicyError("Canned fallback scripts are disabled. Supply a topic-specific reviewed script.")

if __name__ == "__main__":
    script = generate_video_script("Ukraine vs Russia", target_duration_seconds=20)
    print(json.dumps(script, indent=2))
