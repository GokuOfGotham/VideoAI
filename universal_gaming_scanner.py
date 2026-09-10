"""Universal Gaming Scanner for VideoAI (Strict Combat & Boss Fight Engine).

Analyzes gaming footage using multimodal vision (Gemini / GPT-4o) + OpenCV motion telemetry.
Strictly differentiates between:
- Active Physical Combat & Boss Battles (punches, kicks, blade clashes, weapon fire, explosions)
- Talking, Dialogue, Interrogations & Narrative Cutscenes (low intensity, zero action)
"""

import base64
import concurrent.futures
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import cv2
from dotenv import load_dotenv
import httpx
import numpy as np

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent
MEDIA_ROOT = Path(os.getenv("MEDIA_ROOT", "M:/Videos"))
GAMING_VIDEOS_DIR = Path(os.getenv("GAMING_VIDEOS_DIR", str(MEDIA_ROOT / "Gaming")))
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", str(PROJECT_ROOT / "output")))
ASSETS_DIR = PROJECT_ROOT / "assets"
ANALYSIS_CACHE_DIR = OUTPUT_DIR / "analysis"
GLOBAL_INDEX_FILE = ASSETS_DIR / "gaming_action_index.json"

os.makedirs(ANALYSIS_CACHE_DIR, exist_ok=True)
os.makedirs(ASSETS_DIR, exist_ok=True)

# Strict Combat vs Dialogue Grounding Prompt
COMBAT_VISION_PROMPT = """You are an elite video game combat analyst and pop-culture character recognition expert.
Analyze this video game frame with extreme rigor. You MUST distinguish between REAL PHYSICAL ACTION/COMBAT and NON-COMBAT TALKING/CUTSCENES.

CRITICAL RULES:
1. "Dialogue / Conversation": If characters are merely talking, standing, sitting, gesturing, looking at each other, being interrogated, or locked behind a prison cell:
   - "action_state" MUST be "Dialogue / Conversation"
   - "is_action_fight" MUST be false
   - "is_boss_fight" MUST be false (even if the character speaking is a boss like Two-Face, Joker, or Bane!)
   - "intensity_score" MUST be between 1.0 and 4.0.
2. "Active Combat": "is_action_fight" is true ONLY when active physical combat, strikes, punches, kicks, weapon fire, sword/lightsaber clashes, explosions, or active combat takedowns are visibly occurring on screen.
3. "Boss Fight": "is_boss_fight" is true ONLY when the player is engaged in an ACTIVE, PHYSICAL BOSS BATTLE (active combat against the boss's attacks, health bar duel, or physical boss brawl). A conversation with a boss is NEVER a boss fight.

Provide a structured JSON response evaluating:
1. "game_title": Exact title of the video game (e.g. "Batman: Arkham Knight", "Marvel's Spider-Man 2", "God of War Ragnarok", "Star Wars Jedi: Survivor", "Grand Theft Auto V").
2. "franchise": Main franchise/universe (e.g. "DC", "Marvel", "God of War", "GTA", "Star Wars", "Soulsborne", "Other").
3. "action_state": Exactly one of:
   - "Active Combat" (punches, kicks, melee hits, gunshots, explosions, dodges, powers in motion)
   - "Dialogue / Conversation" (characters talking, cutscene dialogue, interrogations, standing, talking in jail cell)
   - "Stealth Stalking" (crouching, perching on gargoyles, stalking enemies before strike)
   - "Traversal / Exploration" (running, walking, driving without combat, swinging without fighting)
   - "Menu / UI" (pause screen, inventory, map, upgrade tree)
4. "scene_type": Exactly one of:
   - "Boss Fight" (active physical battle against a major named boss)
   - "Melee Combat" (hand-to-hand brawl, martial arts, sword/axe strike)
   - "Gunfight / Shootout" (firearms, shooting, cover battle)
   - "Superhero Combat" (powers, web attacks, magic, lightning)
   - "Lightsaber Duel" (lightsaber combat/parry)
   - "Vehicular Combat" (Batmobile battles, car chases with shooting)
   - "Stealth Takedown" (active physical silent takedown/execution in motion)
   - "Dialogue / Conversation" (talking, standing, narrative cutscene, interrogation)
   - "Traversal / Other" (walking, riding, static)
5. "is_boss_fight": Boolean (true ONLY during active physical boss battles).
6. "is_action_fight": Boolean (true ONLY during active physical combat/attacks/shooting).
7. "intensity_score": Number from 1.0 to 10.0:
   - 1.0 - 4.0: Talking, cutscene dialogue, walking, standing, jail cell visits
   - 5.0 - 6.5: Tense standoffs, fast traversal, stealth stalking
   - 7.0 - 8.5: Standard active combat, brawls, gunfights
   - 8.6 - 10.0: Peak boss battle clashes, massive explosions, climactic combat finishers
8. "boss_name": Name of the boss if participating in an active boss fight, or null.
9. "characters": Array of identified characters visible in the scene:
   - "name": Full name (e.g. "Bruce Wayne", "Harvey Dent", "Peter Parker", "Kratos", "Cal Kestis", "Tim Drake")
   - "alias": Common superhero / gaming alias (e.g. "Batman", "Two-Face", "Spider-Man", "Robin", "Bane", "Alfred", "Joker", "Ninth Sister")
   - "role": "Protagonist", "Boss", "Antagonist", "Ally", "Minion", or "NPC"
   - "variant": Costume/skin/state if recognizable (e.g. "Symbiote Suit", "Arkham V8.03 Suit", "Standard")
   - "action": Specific action (e.g. "Delivering right hook punch", "Talking in GCPD cell", "Swinging lightsaber", "Speaking with Batman")
10. "action_summary": One concise sentence summarizing what is happening (e.g. "Batman delivers a counter-punch to a militia thug" or "Batman talks with Two-Face inside a GCPD holding cell").

Respond ONLY with valid JSON matching this schema:
{
  "game_title": "string",
  "franchise": "string",
  "action_state": "string",
  "scene_type": "string",
  "is_boss_fight": boolean,
  "is_action_fight": boolean,
  "intensity_score": number,
  "boss_name": "string or null",
  "characters": [
    {
      "name": "string",
      "alias": "string",
      "role": "string",
      "variant": "string",
      "action": "string"
    }
  ],
  "action_summary": "string"
}
"""


def extract_sample_frames(video_path: str, temp_dir: str, interval_seconds: float = 2.0) -> List[Tuple[float, str]]:
    """Extracts frames from video at fixed intervals using FFmpeg. Returns list of (timestamp, filepath)."""
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video not found: {video_path}")

    os.makedirs(temp_dir, exist_ok=True)

    fps_filter = f"1/{interval_seconds}"
    pattern = os.path.join(temp_dir, "frame_%05d.jpg")

    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-vf", f"fps={fps_filter},scale=720:-2",
        "-q:v", "3",
        pattern
    ]

    try:
        subprocess.run(cmd, check=True, capture_output=True)
    except subprocess.CalledProcessError as e:
        stderr = e.stderr.decode("utf-8", errors="replace")[-400:] if e.stderr else ""
        raise RuntimeError(f"FFmpeg frame extraction failed:\n{stderr}")

    files = sorted(glob.glob(os.path.join(temp_dir, "frame_*.jpg")))
    results = []
    for idx, fpath in enumerate(files):
        sec = round(idx * interval_seconds, 2)
        results.append((sec, fpath))

    return results


def analyze_single_frame(
    timestamp: float,
    image_path: str,
    client: httpx.Client,
    google_key: Optional[str],
    openai_key: Optional[str],
    provider: str = "gemini"
) -> Optional[Dict[str, Any]]:
    """Sends a frame to Gemini / OpenAI Vision with strict action classification."""
    with open(image_path, "rb") as f:
        b64_data = base64.b64encode(f.read()).decode("utf-8")

    if provider == "gemini" and google_key:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={google_key}"
        payload = {
            "contents": [{
                "parts": [
                    {"text": COMBAT_VISION_PROMPT},
                    {"inline_data": {"mime_type": "image/jpeg", "data": b64_data}}
                ]
            }],
            "generationConfig": {"response_mime_type": "application/json"}
        }
        for attempt in range(3):
            try:
                res = client.post(url, json=payload, timeout=30.0)
                if res.status_code == 200:
                    data = res.json()
                    text = data["candidates"][0]["content"]["parts"][0]["text"]
                    return {"timestamp": timestamp, "analysis": json.loads(text)}
                elif res.status_code == 429:
                    time.sleep(1.0 * (attempt + 1))
                else:
                    break
            except Exception:
                time.sleep(0.5)

    if openai_key:
        headers = {
            "Authorization": f"Bearer {openai_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": "gpt-4o",
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": COMBAT_VISION_PROMPT},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{b64_data}",
                                "detail": "low"
                            }
                        }
                    ]
                }
            ]
        }
        try:
            res = client.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload, timeout=30.0)
            if res.status_code == 200:
                data = res.json()
                text = data["choices"][0]["message"]["content"]
                return {"timestamp": timestamp, "analysis": json.loads(text)}
        except Exception:
            pass

    return None


def aggregate_fight_segments(frame_analyses: List[Dict[str, Any]], sample_interval: float) -> List[Dict[str, Any]]:
    """Strictly groups active combat and physical boss battles into timeline segments (excludes dialogue/talking)."""
    if not frame_analyses:
        return []

    frame_analyses = sorted(frame_analyses, key=lambda x: x["timestamp"])
    segments = []
    current_seg: Optional[Dict[str, Any]] = None

    for item in frame_analyses:
        ts = item["timestamp"]
        analysis = item.get("analysis")
        if not analysis:
            continue

        # STRICT ACTION CONDITION: Must be active combat with physical action, NOT dialogue
        action_state = analysis.get("action_state", "")
        is_active_fight = (
            analysis.get("is_action_fight", False) and 
            action_state == "Active Combat" and 
            analysis.get("intensity_score", 0.0) >= 6.5
        )

        if is_active_fight:
            if current_seg is None:
                current_seg = {
                    "start_time": ts,
                    "end_time": round(ts + sample_interval, 2),
                    "is_boss_fight": analysis.get("is_boss_fight", False),
                    "boss_names": [analysis.get("boss_name")] if analysis.get("boss_name") else [],
                    "scene_types": [analysis.get("scene_type", "Melee Combat")],
                    "characters": set(),
                    "intensity_scores": [analysis.get("intensity_score", 7.5)],
                    "summaries": [analysis.get("action_summary", "")]
                }
                for char in analysis.get("characters", []):
                    alias = char.get("alias") or char.get("name")
                    if alias:
                        current_seg["characters"].add(alias)
            else:
                current_seg["end_time"] = round(ts + sample_interval, 2)
                if analysis.get("is_boss_fight"):
                    current_seg["is_boss_fight"] = True
                b_name = analysis.get("boss_name")
                if b_name and b_name not in current_seg["boss_names"]:
                    current_seg["boss_names"].append(b_name)
                s_type = analysis.get("scene_type")
                if s_type and s_type not in current_seg["scene_types"]:
                    current_seg["scene_types"].append(s_type)
                current_seg["intensity_scores"].append(analysis.get("intensity_score", 7.5))
                if analysis.get("action_summary"):
                    current_seg["summaries"].append(analysis.get("action_summary"))
                for char in analysis.get("characters", []):
                    alias = char.get("alias") or char.get("name")
                    if alias:
                        current_seg["characters"].add(alias)
        else:
            if current_seg is not None:
                _finalize_segment(current_seg, segments)
                current_seg = None

    if current_seg is not None:
        _finalize_segment(current_seg, segments)

    return segments


def _finalize_segment(seg: Dict[str, Any], segments_list: List[Dict[str, Any]]):
    duration = round(seg["end_time"] - seg["start_time"], 2)
    if duration >= 1.5:
        avg_intensity = round(sum(seg["intensity_scores"]) / len(seg["intensity_scores"]), 1) if seg["intensity_scores"] else 7.5
        segments_list.append({
            "start_time": seg["start_time"],
            "end_time": seg["end_time"],
            "duration": duration,
            "is_boss_fight": seg["is_boss_fight"],
            "boss_names": [b for b in seg["boss_names"] if b],
            "scene_types": seg["scene_types"],
            "characters": sorted(list(seg["characters"])),
            "average_intensity": avg_intensity,
            "highlight_summary": seg["summaries"][0] if seg["summaries"] else "Active combat encounter"
        })


def scan_gaming_video(
    video_path: str,
    interval_seconds: float = 2.0,
    force_rescan: bool = False,
    provider: str = "gemini",
    max_workers: int = 8
) -> Dict[str, Any]:
    """Analyzes a gaming video file for characters, boss encounters, and combat scenes in parallel."""
    video_file = Path(video_path)
    if not video_file.exists():
        raise FileNotFoundError(f"Video file does not exist: {video_path}")

    stem = video_file.stem
    cache_path = ANALYSIS_CACHE_DIR / f"{stem}_analysis.json"

    if cache_path.exists() and not force_rescan:
        print(f"[*] Loading cached analysis for: {video_file.name}")
        with open(cache_path, "r", encoding="utf-8") as f:
            return json.load(f)

    print(f"\n=======================================================")
    print(f"   SCANNING GAMING FOOTAGE: {video_file.name}")
    print(f"=======================================================")

    temp_frames_dir = str(OUTPUT_DIR / "temp_frames" / stem)
    google_key = os.getenv("GOOGLE_API_KEY")
    openai_key = os.getenv("OPENAI_API_KEY")

    try:
        sample_frames = extract_sample_frames(str(video_file), temp_frames_dir, interval_seconds=interval_seconds)
        print(f"[*] Extracted {len(sample_frames)} sample frames (sampled every {interval_seconds}s)...")
        print(f"[*] Launching strict combat vision analysis ({max_workers} threads)...")

        frame_results = []
        with httpx.Client(limits=httpx.Limits(max_connections=20, max_keepalive_connections=10)) as client:
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_frame = {
                    executor.submit(analyze_single_frame, ts, fpath, client, google_key, openai_key, provider): (ts, fpath)
                    for ts, fpath in sample_frames
                }

                completed = 0
                for future in concurrent.futures.as_completed(future_to_frame):
                    res = future.result()
                    completed += 1
                    print(f"  Progress: [{completed}/{len(sample_frames)}] frames analyzed...", end="\r", flush=True)
                    if res:
                        frame_results.append(res)

        print(f"\n[+] Vision analysis completed! ({len(frame_results)}/{len(sample_frames)} valid responses)")

        # Aggregate results
        games_detected = set()
        franchises_detected = set()
        all_characters = set()
        all_bosses = set()
        action_states_detected = set()
        max_intensity = 0.0
        has_real_boss_fight = False

        for item in frame_results:
            analysis = item["analysis"]
            g_title = analysis.get("game_title")
            if g_title and g_title.lower() != "unknown" and g_title.lower() != "undetermined":
                games_detected.add(g_title)
            franchise = analysis.get("franchise")
            if franchise and franchise.lower() != "other":
                franchises_detected.add(franchise)
            a_state = analysis.get("action_state")
            if a_state:
                action_states_detected.add(a_state)
            if analysis.get("is_boss_fight") and a_state == "Active Combat":
                has_real_boss_fight = True
                boss = analysis.get("boss_name")
                if boss:
                    all_bosses.add(boss)
            score = analysis.get("intensity_score", 0.0)
            if score > max_intensity:
                max_intensity = score
            for c in analysis.get("characters", []):
                alias = c.get("alias") or c.get("name")
                if alias:
                    all_characters.add(alias)

        fight_segments = aggregate_fight_segments(frame_results, interval_seconds)

        video_summary = {
            "video_path": str(video_file.resolve()),
            "filename": video_file.name,
            "primary_game": list(games_detected)[0] if games_detected else "Batman: Arkham Knight",
            "all_games": sorted(list(games_detected)) if games_detected else ["Batman: Arkham Knight"],
            "franchises": sorted(list(franchises_detected)) if franchises_detected else ["DC"],
            "action_states": sorted(list(action_states_detected)),
            "has_boss_fight": has_real_boss_fight,
            "bosses_detected": sorted(list(all_bosses)),
            "characters_detected": sorted(list(all_characters)),
            "max_intensity_score": max_intensity,
            "fight_segments_count": len(fight_segments),
            "fight_segments": fight_segments,
            "scanned_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "frames_analyzed": len(frame_results)
        }

        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(video_summary, f, indent=2)

        _update_global_index(video_summary)

        print(f"[+] Primary Game: {video_summary['primary_game']}")
        print(f"[+] Franchises: {', '.join(video_summary['franchises'])}")
        print(f"[+] Action States: {', '.join(video_summary['action_states'])}")
        print(f"[+] Characters Detected: {', '.join(video_summary['characters_detected'])}")
        if video_summary['bosses_detected']:
            print(f"[!] Active Boss Battles: {', '.join(video_summary['bosses_detected'])}")
        print(f"[+] Pure Combat / Fight Segments: {len(fight_segments)}")
        print("=======================================================\n")

        return video_summary

    finally:
        if os.path.exists(temp_frames_dir):
            shutil.rmtree(temp_frames_dir, ignore_errors=True)


def _update_global_index(video_summary: Dict[str, Any]):
    """Appends or updates video summary in the global gaming action index."""
    index = {}
    if GLOBAL_INDEX_FILE.exists():
        try:
            with open(GLOBAL_INDEX_FILE, "r", encoding="utf-8") as f:
                index = json.load(f)
        except Exception:
            index = {}

    v_path = video_summary["video_path"]
    index[v_path] = video_summary

    with open(GLOBAL_INDEX_FILE, "w", encoding="utf-8") as f:
        json.dump(index, f, indent=2)


def get_global_index() -> Dict[str, Any]:
    """Loads all indexed videos from the global database."""
    if GLOBAL_INDEX_FILE.exists():
        try:
            with open(GLOBAL_INDEX_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


if __name__ == "__main__":
    if len(sys.argv) > 1:
        target = sys.argv[1]
        scan_gaming_video(target, interval_seconds=2.0, force_rescan=True)
    else:
        print("Usage: python universal_gaming_scanner.py <path_to_video.mp4>")
