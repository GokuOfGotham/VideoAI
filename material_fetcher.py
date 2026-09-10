"""Material Fetcher for VideoAI.

Downloads HD stock videos from Pexels / Pixabay APIs, cuts licence-filtered
b-roll from YouTube, or selects local footage matching scene keywords, caching
clips in assets/materials/.
Supports intelligent character and boss fight recognition retrieval.
"""

import glob
import json
import os
import random
import re
from pathlib import Path
from typing import Dict, List, Optional
import requests
from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent
MATERIALS_DIR = PROJECT_ROOT / "assets" / "materials"
MEDIA_ROOT = Path(os.getenv("MEDIA_ROOT", "M:/Videos"))
MILITARY_VIDEOS_DIR = Path(os.getenv("MILITARY_VIDEOS_DIR", str(MEDIA_ROOT / "US Military")))
GAMING_VIDEOS_DIR = Path(os.getenv("GAMING_VIDEOS_DIR", str(MEDIA_ROOT / "Gaming")))
GLOBAL_INDEX_FILE = PROJECT_ROOT / "assets" / "gaming_action_index.json"

os.makedirs(MATERIALS_DIR, exist_ok=True)


def fetch_material_for_scene(
    keywords: str,
    target_duration: float = 5.0,
    aspect_ratio: str = "9:16",
    filter_no_faces: bool = False
) -> Optional[str]:
    """Fetches a video file path matching keywords.

    Tries Gaming / Character indexed footage first if gaming/comic keywords detected,
    then Pexels/Pixabay stock APIs, then YouTube b-roll, and falls back to local
    media directories. YOUTUBE_BROLL_PRIORITY moves the YouTube tier ahead of the
    stock APIs ("first") or disables it ("off").
    """
    kw_lower = keywords.lower()
    
    # Check if this is a gaming / character / boss fight request
    is_gaming = any(w in kw_lower for w in [
        "batman", "robin", "bane", "alfred", "joker", "kratos", "thor", "spider-man",
        "spiderman", "miles", "venom", "kraven", "gta", "trevor", "michael", "franklin",
        "boss fight", "combat", "fight", "gameplay", "arkham", "ragnarok", "jedi", "cal kestis"
    ])

    if is_gaming:
        gaming_clip = _search_indexed_gaming_media(keywords)
        if gaming_clip and os.path.exists(gaming_clip):
            return gaming_clip

    pexels_key = os.getenv("PEXELS_API_KEY")
    pixabay_key = os.getenv("PIXABAY_API_KEY")
    broll_priority = os.getenv("YOUTUBE_BROLL_PRIORITY", "fallback").strip().lower()

    # Space scenes go to NASA/SpaceX first: the footage is public domain and a
    # far better match than whatever "rocket" returns from a stock library.
    space_clip = _fetch_space_media(keywords, target_duration)
    if space_clip and os.path.exists(space_clip):
        return space_clip

    if broll_priority == "first":
        clip_path = _fetch_youtube_broll(keywords, target_duration)
        if clip_path and os.path.exists(clip_path):
            return clip_path

    if pexels_key:
        clip_path = _fetch_pexels_video(keywords, pexels_key, aspect_ratio)
        if clip_path and os.path.exists(clip_path):
            return clip_path

    if pixabay_key:
        clip_path = _fetch_pixabay_video(keywords, pixabay_key)
        if clip_path and os.path.exists(clip_path):
            return clip_path

    if broll_priority not in ("first", "off"):
        clip_path = _fetch_youtube_broll(keywords, target_duration)
        if clip_path and os.path.exists(clip_path):
            return clip_path

    # Local footage fallback
    return _search_local_media(keywords)


def _fetch_space_media(keywords: str, target_duration: float) -> Optional[str]:
    """Sources NASA/SpaceX media for space scenes, or None to fall through.

    Imported lazily and skipped entirely for non-space keywords, so the tier
    costs nothing on the gaming and military scenes that dominate this project.
    """
    if os.getenv("SPACE_MEDIA_ENABLED", "1").strip().lower() in ("0", "false", "no"):
        return None

    try:
        from space_media_sourcer import fetch_space_media, looks_like_space
    except ImportError as exc:
        print(f"[MaterialFetcher] Space media tier unavailable ({exc}).")
        return None

    if not looks_like_space(keywords):
        return None

    return fetch_space_media(keywords, target_duration=target_duration)


def _fetch_youtube_broll(keywords: str, target_duration: float) -> Optional[str]:
    """Cuts a b-roll clip from YouTube, or returns None so the caller falls through.

    Imported lazily: yt-dlp is optional, and a machine without it should still
    run the stock and local tiers normally.
    """
    try:
        from youtube_broll import fetch_youtube_broll
    except ImportError as exc:
        print(f"[MaterialFetcher] YouTube b-roll tier unavailable ({exc}).")
        return None

    return fetch_youtube_broll(keywords, target_duration=target_duration)


def _search_indexed_gaming_media(keywords: str) -> Optional[str]:
    """Queries the gaming character & fight index for matching video segments."""
    if not GLOBAL_INDEX_FILE.exists():
        return None

    try:
        with open(GLOBAL_INDEX_FILE, "r", encoding="utf-8") as f:
            index = json.load(f)

        words = [w.lower() for w in re.findall(r"\w+", keywords) if len(w) > 2]
        candidates = []

        for v_path, data in index.items():
            if not os.path.exists(v_path):
                continue

            chars = [c.lower() for c in data.get("characters_detected", [])]
            bosses = [b.lower() for b in data.get("bosses_detected", [])]
            games = [g.lower() for g in data.get("all_games", [])]
            franchises = [f.lower() for f in data.get("franchises", [])]
            all_meta = chars + bosses + games + franchises + [data.get("filename", "").lower()]

            match_score = sum(1 for w in words if any(w in m for m in all_meta))
            if match_score > 0:
                candidates.append((match_score, v_path))

        if candidates:
            candidates.sort(key=lambda x: x[0], reverse=True)
            return candidates[0][1]

    except Exception as e:
        print(f"[MaterialFetcher] Gaming index search failed ({e}).")

    return None


def _fetch_pexels_video(query: str, api_key: str, aspect_ratio: str = "9:16") -> Optional[str]:
    """Queries Pexels Video API and downloads the best matching clip."""
    orientation = "portrait" if aspect_ratio in ("9:16", "portrait") else "landscape"
    url = f"https://api.pexels.com/videos/search?query={requests.utils.quote(query)}&orientation={orientation}&per_page=5"
    headers = {"Authorization": api_key}

    try:
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        videos = data.get("videos", [])
        if not videos:
            fallback_query = query.split()[0] if query else "military"
            url_fb = f"https://api.pexels.com/videos/search?query={fallback_query}&per_page=5"
            resp = requests.get(url_fb, headers=headers, timeout=15)
            videos = resp.json().get("videos", [])

        if not videos:
            return None

        selected = random.choice(videos[:3])
        video_files = selected.get("video_files", [])
        if not video_files:
            return None

        video_files.sort(key=lambda v: v.get("width", 0) * v.get("height", 0), reverse=True)
        target_file = video_files[0]["link"]

        file_id = selected["id"]
        save_path = str(MATERIALS_DIR / f"pexels_{file_id}.mp4")

        if os.path.exists(save_path) and os.path.getsize(save_path) > 0:
            return save_path

        print(f"[MaterialFetcher] Downloading Pexels video {file_id} for '{query}'...")
        v_resp = requests.get(target_file, stream=True, timeout=30)
        v_resp.raise_for_status()
        with open(save_path, "wb") as f:
            for chunk in v_resp.iter_content(chunk_size=64 * 1024):
                if chunk:
                    f.write(chunk)

        return save_path

    except Exception as e:
        print(f"[MaterialFetcher] Pexels fetch failed ({e}).")
        return None


def _fetch_pixabay_video(query: str, api_key: str) -> Optional[str]:
    """Queries Pixabay Video API and downloads matching video clip."""
    url = f"https://pixabay.com/api/videos/?key={api_key}&q={requests.utils.quote(query)}&per_page=5"

    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        hits = resp.json().get("hits", [])
        if not hits:
            return None

        selected = random.choice(hits[:3])
        videos_data = selected.get("videos", {})
        target = videos_data.get("medium") or videos_data.get("large") or videos_data.get("small")
        if not target:
            return None

        file_id = selected["id"]
        save_path = str(MATERIALS_DIR / f"pixabay_{file_id}.mp4")

        if os.path.exists(save_path) and os.path.getsize(save_path) > 0:
            return save_path

        print(f"[MaterialFetcher] Downloading Pixabay video {file_id}...")
        v_resp = requests.get(target["url"], stream=True, timeout=30)
        v_resp.raise_for_status()
        with open(save_path, "wb") as f:
            for chunk in v_resp.iter_content(chunk_size=64 * 1024):
                if chunk:
                    f.write(chunk)

        return save_path
    except Exception as e:
        print(f"[MaterialFetcher] Pixabay fetch failed ({e}).")
        return None


def _search_local_media(keywords: str) -> Optional[str]:
    """Searches local media directories for videos matching keywords."""
    is_military = any(w in keywords.lower() for w in ["military", "war", "defense", "jet", "tank", "soldier", "ukraine", "russia", "navy", "flight", "stealth", "radar", "kinetic"])

    if is_military and MILITARY_VIDEOS_DIR.exists():
        mil_videos = glob.glob(str(MILITARY_VIDEOS_DIR / "*.mp4"))
        if mil_videos:
            return random.choice(mil_videos)

    search_dirs = [
        GAMING_VIDEOS_DIR,
        MILITARY_VIDEOS_DIR,
        MEDIA_ROOT,
        MEDIA_ROOT / "Nature",
        MEDIA_ROOT / "Life"
    ]

    all_videos = []
    for d in search_dirs:
        if d.exists():
            all_videos.extend(glob.glob(str(d / "**/*.mp4"), recursive=True))
            all_videos.extend(glob.glob(str(d / "**/*.mov"), recursive=True))

    if not all_videos:
        return None

    # Check for keyword matches in filename
    words = [w.lower() for w in re.findall(r"\w+", keywords) if len(w) > 3]
    matches = []
    for vid in all_videos:
        fname = Path(vid).stem.lower()
        if any(w in fname for w in words):
            matches.append(vid)

    if matches:
        return random.choice(matches)

    return random.choice(all_videos)


if __name__ == "__main__":
    clip = fetch_material_for_scene("Batman vs Bane boss fight combat", target_duration=5.0)
    print(f"Fetched material clip: {clip}")
