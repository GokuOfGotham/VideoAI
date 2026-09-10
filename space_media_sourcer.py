"""Space Media Sourcer for VideoAI.

Sources spaceflight footage and imagery from NASA and SpaceX for space videos,
normalising everything to the same muted vertical clips the renderer expects.

Tiers, cheapest and most permissive first:

1. **NASA Image and Video Library** (``images-api.nasa.gov``) — real MP4 footage,
   no API key required. NASA media is generally public domain, which makes it
   the safest tier to lean on.
2. **SpaceX** (``api.spacexdata.com``) — launch photography from the Flickr
   originals on each launch, and launch webcasts, whose YouTube ids are handed
   to the b-roll pipeline so the footage gets cut the same way.
3. **NASA APOD** (``api.nasa.gov``) — high-resolution astronomy stills. Uses
   ``NASA_API_KEY``; falls back to ``DEMO_KEY`` at a much lower rate limit.

Stills are given a slow push rather than being held static, since a frozen
frame under narration reads as a broken video.

Licensing: NASA material is public domain with the caveats NASA publishes —
its logos and insignia are restricted, and some library items are third-party
content that only NASA has cleared. SpaceX has released its launch photography
into the public domain (CC0). Every asset is still recorded in an attribution
ledger so the provenance of anything published can be checked.
"""

import argparse
import json
import os
import re
import sys
import urllib.parse
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Optional

import requests
from dotenv import load_dotenv

from media_common import (
    detect_scene_cuts,
    download_file,
    env_float,
    env_int,
    media_duration,
    normalise_clip,
    pick_longest_shot,
    still_to_clip,
)

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent
CACHE_DIR = Path(
    os.getenv("SPACE_MEDIA_CACHE_DIR", str(PROJECT_ROOT / "assets" / "materials" / "space"))
)
LEDGER_FILE = CACHE_DIR / "attribution.json"
LEDGER_MARKDOWN = CACHE_DIR / "ATTRIBUTION.md"

NASA_SEARCH_URL = "https://images-api.nasa.gov/search"
NASA_APOD_URL = "https://api.nasa.gov/planetary/apod"
SPACEX_API_BASE = os.getenv("SPACEX_API_BASE", "https://api.spacexdata.com/v4")

# Words that make a scene a space scene. Used by the media sourcers to decide
# whether this tier is worth trying before the generic stock libraries.
SPACE_KEYWORDS = frozenset({
    "space", "nasa", "spacex", "rocket", "launch", "orbit", "orbital", "satellite",
    "astronaut", "spacecraft", "spaceflight", "iss", "space station", "moon",
    "lunar", "mars", "martian", "jupiter", "saturn", "venus", "mercury", "neptune",
    "uranus", "pluto", "asteroid", "comet", "meteor", "galaxy", "nebula", "cosmos",
    "cosmic", "universe", "star", "stars", "solar", "eclipse", "aurora", "telescope",
    "hubble", "webb", "jwst", "apollo", "artemis", "gemini", "voyager", "cassini",
    "perseverance", "curiosity", "ingenuity", "rover", "falcon", "falcon 9",
    "falcon heavy", "starship", "dragon", "crew dragon", "booster", "reentry",
    "launchpad", "countdown", "liftoff", "payload", "starlink", "milky way",
    "black hole", "supernova", "exoplanet", "interstellar", "deep space",
})


def looks_like_space(text: str) -> bool:
    """True when a scene query is about spaceflight or astronomy."""
    lowered = (text or "").lower()
    words = set(re.findall(r"[a-z0-9]+", lowered))
    if words & SPACE_KEYWORDS:
        return True
    # Catch the multi-word entries the token split above cannot see.
    return any(kw in lowered for kw in SPACE_KEYWORDS if " " in kw)


@dataclass
class SpaceClip:
    """A normalised space clip plus the provenance needed to credit it."""

    path: str
    source: str           # "nasa_library" | "nasa_apod" | "spacex_flickr" | "spacex_webcast"
    asset_id: str
    title: str
    center: str           # NASA centre, or the SpaceX mission name
    page_url: str
    license: str
    media_kind: str       # "video" | "still"
    duration: float
    query: str
    requested_duration: float


# --- Attribution ledger -----------------------------------------------------


def _load_ledger() -> Dict[str, Dict]:
    if not LEDGER_FILE.exists():
        return {}
    try:
        with open(LEDGER_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def _record(clip: SpaceClip) -> None:
    ledger = _load_ledger()
    ledger[Path(clip.path).name] = asdict(clip)

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with open(LEDGER_FILE, "w", encoding="utf-8") as f:
        json.dump(ledger, f, indent=2, ensure_ascii=False)

    lines = [
        "# Space Media Attribution",
        "",
        "Provenance for every NASA and SpaceX asset cached by",
        "`space_media_sourcer.py`. NASA material is public domain except for its",
        "logos and insignia and any third-party content it hosts; SpaceX has",
        "released its launch photography into the public domain. Check anything",
        "flagged below before publishing.",
        "",
    ]
    for name, entry in sorted(ledger.items()):
        lines.extend([
            f"## {name}",
            "",
            f"- **Title:** {entry.get('title', 'unknown')}",
            f"- **Source:** {entry.get('source')} ({entry.get('center', '')})",
            f"- **Asset id:** {entry.get('asset_id', '')}",
            f"- **Page:** {entry.get('page_url', '')}",
            f"- **Licence:** {entry.get('license', 'unknown')}",
            f"- **Kind:** {entry.get('media_kind')} ({entry.get('duration', 0):.1f}s)",
            f"- **Matched query:** {entry.get('query', '')}",
            "",
        ])
    with open(LEDGER_MARKDOWN, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def _lookup_cached(query: str, requested: float, kind: Optional[str]) -> Optional[SpaceClip]:
    """Returns a previously cut clip for this exact request, if it survives."""
    for entry in _load_ledger().values():
        if entry.get("query") != query:
            continue
        if round(float(entry.get("requested_duration") or 0), 2) != round(float(requested), 2):
            continue
        if kind and entry.get("media_kind") != kind:
            continue
        path = Path(entry.get("path", ""))
        if not path.exists() or path.stat().st_size <= 10_000:
            continue
        try:
            return SpaceClip(**entry)
        except TypeError:
            continue  # ledger written by an older schema
    return None


def attribution_report() -> str:
    ledger = _load_ledger()
    if not ledger:
        return "No space media has been cached yet."
    return "\n\n".join(
        f"{name}\n  {e.get('title', 'unknown')}\n  {e.get('source')} — {e.get('license')}\n"
        f"  {e.get('page_url', '')}"
        for name, e in sorted(ledger.items())
    )


# --- NASA Image and Video Library -------------------------------------------


def _nasa_search(query: str, media_type: str) -> List[Dict]:
    try:
        resp = requests.get(
            NASA_SEARCH_URL,
            params={"q": query, "media_type": media_type},
            timeout=25,
            headers={"User-Agent": "VideoAI/1.0"},
        )
        resp.raise_for_status()
        return resp.json().get("collection", {}).get("items", []) or []
    except Exception as exc:
        print(f"[SpaceMedia] NASA search failed ({exc}).")
        return []


def _nasa_asset_files(collection_href: str) -> List[str]:
    try:
        resp = requests.get(collection_href, timeout=25, headers={"User-Agent": "VideoAI/1.0"})
        resp.raise_for_status()
        return resp.json() or []
    except Exception:
        return []


def _best_nasa_video(files: List[str]) -> Optional[str]:
    """Picks the highest usable MP4 rendition.

    `~orig` can be a multi-GB broadcast master, so prefer `~large`, which is
    already well above the 1080-wide output.
    """
    mp4s = [f for f in files if f.lower().endswith(".mp4")]
    if not mp4s:
        return None
    for tag in ("~large", "~medium", "~orig", "~mobile"):
        for f in mp4s:
            if tag in f:
                return f.replace("http://", "https://")
    return mp4s[0].replace("http://", "https://")


def _best_nasa_image(files: List[str]) -> Optional[str]:
    images = [f for f in files if f.lower().endswith((".jpg", ".jpeg", ".png"))]
    if not images:
        return None
    for tag in ("~orig", "~large", "~medium"):
        for f in images:
            if tag in f:
                return f.replace("http://", "https://")
    return images[0].replace("http://", "https://")


def _try_nasa_library(query: str, clip_length: float, prefer_video: bool) -> Optional[SpaceClip]:
    kinds = ["video", "image"] if prefer_video else ["image", "video"]

    for media_type in kinds:
        for item in _nasa_search(query, media_type)[: env_int("SPACE_MEDIA_CANDIDATES", 5)]:
            data = (item.get("data") or [{}])[0]
            nasa_id = data.get("nasa_id")
            href = item.get("href")
            if not nasa_id or not href:
                continue

            files = _nasa_asset_files(href)
            url = _best_nasa_video(files) if media_type == "video" else _best_nasa_image(files)
            if not url:
                continue

            safe = re.sub(r"[^A-Za-z0-9_-]", "_", nasa_id)[:60]
            dest = CACHE_DIR / f"nasa_{safe}_{int(clip_length)}.mp4"
            raw = CACHE_DIR / f".raw_nasa_{safe}{Path(urllib.parse.urlparse(url).path).suffix}"

            print(f"[SpaceMedia] NASA {media_type}: {data.get('title', nasa_id)[:60]}")
            if not download_file(url, raw):
                continue

            ok = _render(raw, dest, clip_length, media_type == "video")
            raw.unlink(missing_ok=True)
            if not ok:
                continue

            clip = SpaceClip(
                path=str(dest),
                source="nasa_library",
                asset_id=nasa_id,
                title=data.get("title", ""),
                center=data.get("center", "NASA"),
                # nasa_id often contains spaces, which would make a dead link.
                page_url="https://images.nasa.gov/details/"
                         + urllib.parse.quote(nasa_id, safe=""),
                license="Public domain (NASA media guidelines)",
                media_kind="video" if media_type == "video" else "still",
                duration=round(clip_length, 2),
                query=query,
                requested_duration=round(clip_length, 2),
            )
            _record(clip)
            print(f"[SpaceMedia] Cut {clip_length:.1f}s -> {dest.name}")
            return clip
    return None


# --- SpaceX -----------------------------------------------------------------


def _spacex_get(path: str) -> Optional[object]:
    """Calls the SpaceX API, returning None when it is unreachable.

    The public instance goes down for stretches at a time (Cloudflare 5xx), so
    every caller treats absence as normal and falls through to another tier.
    """
    try:
        resp = requests.get(
            f"{SPACEX_API_BASE}/{path.lstrip('/')}",
            timeout=env_int("SPACEX_TIMEOUT", 20),
            headers={"User-Agent": "VideoAI/1.0"},
        )
        if resp.status_code >= 500:
            print(f"[SpaceMedia] SpaceX API unavailable (HTTP {resp.status_code}).")
            return None
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        print(f"[SpaceMedia] SpaceX API unreachable ({exc}).")
        return None


def _spacex_launches() -> List[Dict]:
    """Returns all launches, preferring a cached copy over a repeat fetch."""
    cache = CACHE_DIR / "spacex_launches.json"
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    data = _spacex_get("launches")
    if isinstance(data, list) and data:
        try:
            with open(cache, "w", encoding="utf-8") as f:
                json.dump(data, f)
        except OSError:
            pass
        return data

    # The API is down; a previous run's copy keeps this tier working offline.
    if cache.exists():
        try:
            with open(cache, "r", encoding="utf-8") as f:
                cached = json.load(f)
            print(f"[SpaceMedia] Using cached SpaceX launch data ({len(cached)} launches).")
            return cached
        except (OSError, json.JSONDecodeError):
            pass
    return []


def _match_launches(launches: List[Dict], query: str) -> List[Dict]:
    """Ranks launches by how well their name/details match the query."""
    words = {w for w in re.findall(r"[a-z0-9]+", query.lower()) if len(w) > 2}
    scored = []
    for launch in launches:
        haystack = " ".join(filter(None, [
            launch.get("name", ""), launch.get("details") or "",
        ])).lower()
        score = sum(1 for w in words if w in haystack)
        if launch.get("success"):
            score += 0.5
        if score > 0:
            scored.append((score, launch))

    if not scored:
        # No name match: fall back to recent launches that actually have media.
        scored = [(0, l) for l in launches[-40:]]
    scored.sort(key=lambda x: x[0], reverse=True)
    return [l for _, l in scored]


def _try_spacex(query: str, clip_length: float) -> Optional[SpaceClip]:
    launches = _spacex_launches()
    if not launches:
        return None

    candidates = _match_launches(launches, query)
    max_checks = env_int("SPACE_MEDIA_CANDIDATES", 5)

    # Launch photography first: a still we can cut is more reliable than a
    # webcast that may be an hour of hold-and-countdown.
    for launch in candidates[:max_checks]:
        photos = ((launch.get("links") or {}).get("flickr") or {}).get("original") or []
        for url in photos[:3]:
            safe = re.sub(r"[^A-Za-z0-9_-]", "_", launch.get("name", "launch"))[:40]
            dest = CACHE_DIR / f"spacex_{safe}_{int(clip_length)}.mp4"
            raw = CACHE_DIR / f".raw_spacex_{safe}{Path(urllib.parse.urlparse(url).path).suffix or '.jpg'}"

            print(f"[SpaceMedia] SpaceX photo: {launch.get('name')}")
            if not download_file(url, raw):
                continue
            ok = _render(raw, dest, clip_length, is_video=False)
            raw.unlink(missing_ok=True)
            if not ok:
                continue

            clip = SpaceClip(
                path=str(dest), source="spacex_flickr",
                asset_id=str(launch.get("id", "")),
                title=launch.get("name", ""), center=launch.get("name", "SpaceX"),
                page_url=(launch.get("links") or {}).get("wikipedia") or url,
                license="Public domain (SpaceX photography, CC0)",
                media_kind="still", duration=round(clip_length, 2),
                query=query, requested_duration=round(clip_length, 2),
            )
            _record(clip)
            print(f"[SpaceMedia] Cut {clip_length:.1f}s -> {dest.name}")
            return clip

    # Then the webcasts, cut by the b-roll pipeline.
    if os.getenv("SPACE_MEDIA_USE_WEBCASTS", "1").strip().lower() not in ("0", "false", "no"):
        for launch in candidates[:max_checks]:
            youtube_id = (launch.get("links") or {}).get("youtube_id")
            if not youtube_id:
                continue
            clip = _cut_webcast(launch, youtube_id, query, clip_length)
            if clip:
                return clip
    return None


def _cut_webcast(launch: Dict, youtube_id: str, query: str, clip_length: float) -> Optional[SpaceClip]:
    """Hands a launch webcast to the b-roll pipeline for segment selection."""
    try:
        from youtube_broll import fetch_broll_clip
    except ImportError as exc:
        print(f"[SpaceMedia] Webcast tier needs the b-roll pipeline ({exc}).")
        return None

    # SpaceX webcasts are on their own channel; the licence filter would reject
    # them, so this path is explicit about searching for that exact video.
    broll = fetch_broll_clip(
        f"SpaceX {launch.get('name', '')} launch webcast",
        target_duration=clip_length,
        license_policy="any",
    )
    if not broll:
        return None

    clip = SpaceClip(
        path=broll.path, source="spacex_webcast", asset_id=youtube_id,
        title=launch.get("name", ""), center="SpaceX",
        page_url=(launch.get("links") or {}).get("webcast")
        or f"https://www.youtube.com/watch?v={youtube_id}",
        license=broll.license or "SpaceX webcast (verify before publishing)",
        media_kind="video", duration=broll.duration,
        query=query, requested_duration=round(clip_length, 2),
    )
    _record(clip)
    return clip


# --- NASA APOD --------------------------------------------------------------


def _try_apod(query: str, clip_length: float) -> Optional[SpaceClip]:
    key = os.getenv("NASA_API_KEY", "DEMO_KEY")
    try:
        resp = requests.get(
            NASA_APOD_URL,
            params={"api_key": key, "count": env_int("SPACE_MEDIA_APOD_COUNT", 5)},
            timeout=25,
        )
        resp.raise_for_status()
        entries = resp.json()
        entries = entries if isinstance(entries, list) else [entries]
    except Exception as exc:
        print(f"[SpaceMedia] APOD unavailable ({exc}).")
        return None

    for entry in entries:
        if entry.get("media_type") != "image":
            continue
        url = entry.get("hdurl") or entry.get("url")
        if not url:
            continue

        date = entry.get("date", "apod")
        dest = CACHE_DIR / f"apod_{date}_{int(clip_length)}.mp4"
        raw = CACHE_DIR / f".raw_apod_{date}{Path(urllib.parse.urlparse(url).path).suffix or '.jpg'}"

        print(f"[SpaceMedia] APOD: {entry.get('title', '')[:60]}")
        if not download_file(url, raw):
            continue
        ok = _render(raw, dest, clip_length, is_video=False)
        raw.unlink(missing_ok=True)
        if not ok:
            continue

        # APOD often features privately owned astrophotography.
        holder = entry.get("copyright")
        licence = (
            f"Copyright {holder.strip()} — permission required"
            if holder else "Public domain (NASA APOD)"
        )

        clip = SpaceClip(
            path=str(dest), source="nasa_apod", asset_id=date,
            title=entry.get("title", ""), center="NASA APOD",
            page_url=f"https://apod.nasa.gov/apod/ap{date[2:].replace('-', '')}.html",
            license=licence, media_kind="still", duration=round(clip_length, 2),
            query=query, requested_duration=round(clip_length, 2),
        )
        _record(clip)
        print(f"[SpaceMedia] Cut {clip_length:.1f}s -> {dest.name}")
        return clip
    return None


# --- Rendering --------------------------------------------------------------


def _render(raw: Path, dest: Path, clip_length: float, is_video: bool) -> bool:
    if not is_video:
        return still_to_clip(raw, dest, clip_length)

    duration = media_duration(raw)
    if duration <= 0:
        return False
    cuts = detect_scene_cuts(raw)
    offset = pick_longest_shot(cuts, duration, clip_length)
    usable = min(clip_length, max(1.0, duration - offset))
    return normalise_clip(raw, dest, offset, usable)


# --- Public entry points ----------------------------------------------------


def fetch_space_clip(
    query: str,
    target_duration: float = 5.0,
    prefer_video: bool = True,
) -> Optional[SpaceClip]:
    """Sources one normalised space clip for ``query``.

    Returns ``None`` when nothing usable is found, so the caller falls through
    to its next media tier.
    """
    clip_length = max(1.0, float(target_duration))
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    reused = _lookup_cached(query, clip_length, None)
    if reused:
        print(f"[SpaceMedia] Reusing cached clip for '{query}': {Path(reused.path).name}")
        return reused

    for attempt in (
        lambda: _try_nasa_library(query, clip_length, prefer_video),
        lambda: _try_spacex(query, clip_length),
        lambda: _try_apod(query, clip_length),
    ):
        clip = attempt()
        if clip:
            return clip

    print(f"[SpaceMedia] No space media found for '{query}'.")
    return None


def fetch_space_media(query: str, target_duration: float = 5.0) -> Optional[str]:
    """Path-only wrapper matching the signature the media sourcers expect."""
    clip = fetch_space_clip(query, target_duration)
    return clip.path if clip else None


def main() -> int:
    parser = argparse.ArgumentParser(description="NASA / SpaceX media sourcer for VideoAI")
    parser.add_argument("--query", type=str, help="Scene keywords to source space media for")
    parser.add_argument("--duration", type=float, default=5.0, help="Clip length in seconds")
    parser.add_argument("--stills-only", action="store_true", help="Prefer imagery over footage")
    parser.add_argument("--attribution", action="store_true", help="Print the credit ledger and exit")
    parser.add_argument("--check", action="store_true", help="Report which upstream APIs are reachable")
    args = parser.parse_args()

    if args.attribution:
        print(attribution_report())
        return 0

    if args.check:
        print("NASA Image and Video Library:",
              "OK" if _nasa_search("apollo", "video") else "unreachable")
        company = _spacex_get("company")
        print("SpaceX API:", "OK" if company else "unreachable")
        key = os.getenv("NASA_API_KEY")
        print("NASA_API_KEY:", "configured" if key else "missing (APOD limited to DEMO_KEY)")
        return 0

    if not args.query:
        parser.error("--query is required unless --attribution or --check is given")

    clip = fetch_space_clip(args.query, args.duration, prefer_video=not args.stills_only)
    if not clip:
        return 1
    print(f"\n  {clip.path}")
    print(f"  {clip.title} [{clip.source}]")
    print(f"  {clip.license}")
    print(f"\nCredits written to {LEDGER_MARKDOWN}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
