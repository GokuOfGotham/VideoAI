"""YouTube B-Roll Pipeline for VideoAI.

Sources supplementary b-roll from YouTube when the stock libraries come up
short. The pipeline searches, filters candidates down to licences that permit
reuse, downloads only the seconds it actually needs, picks the longest
uninterrupted shot inside that window, and normalises the result to a muted
vertical clip that drops straight into the render stage.

B-roll is deliberately video-only: narration and scored music are added later
by the renderer, so the source audio is never downloaded or muxed.

Every clip that reaches the cache is recorded in an attribution ledger
(``attribution.json`` plus a readable ``ATTRIBUTION.md``) so Creative Commons
credit requirements can be satisfied at publish time.

Licensing: defaults to ``YOUTUBE_BROLL_LICENSE=cc``, which keeps only videos
YouTube reports as Creative Commons. Setting it to ``any`` widens the pool to
standard-licence uploads -- those are *not* cleared for reuse, and confirming
rights on anything published remains your responsibility.
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.parse
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent
CACHE_DIR = Path(
    os.getenv("YOUTUBE_BROLL_CACHE_DIR", str(PROJECT_ROOT / "assets" / "materials" / "youtube"))
)
LEDGER_FILE = CACHE_DIR / "attribution.json"
LEDGER_MARKDOWN = CACHE_DIR / "ATTRIBUTION.md"

# YouTube's own "Creative Commons" search filter. It biases the result page so
# the licence pass has more to work with; every candidate is still verified
# against its reported licence, so a stale value here only costs recall.
_CC_SEARCH_FILTER = "EgIwAQ%3D%3D"

_CC_LICENCE_MARKER = "creative commons"


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, "") or default)
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, "") or default)
    except ValueError:
        return default


def _target_resolution() -> Tuple[int, int]:
    raw = os.getenv("YOUTUBE_BROLL_RESOLUTION", "1080x1920").lower().strip()
    match = re.fullmatch(r"(\d+)\s*x\s*(\d+)", raw)
    if not match:
        return 1080, 1920
    return int(match.group(1)), int(match.group(2))


@dataclass
class BRollClip:
    """A normalised b-roll clip plus the provenance needed to credit it."""

    path: str
    video_id: str
    title: str
    channel: str
    channel_url: str
    webpage_url: str
    license: str
    source_start: float
    source_end: float
    duration: float
    query: str
    # What the caller asked for, as opposed to the length actually cut. Keyed
    # on alongside the query so a repeat request finds this clip again.
    requested_duration: float

    @property
    def requires_attribution(self) -> bool:
        return _CC_LICENCE_MARKER in (self.license or "").lower()


class YouTubeBRollError(RuntimeError):
    """Raised when the pipeline cannot run at all (missing yt-dlp, etc.)."""


def _import_yt_dlp():
    try:
        import yt_dlp
    except ImportError as exc:
        raise YouTubeBRollError(
            "yt-dlp is not installed. Install it with 'pip install yt-dlp' "
            "(or 'uv sync') to enable the YouTube b-roll pipeline."
        ) from exc
    return yt_dlp


# --- Search & candidate filtering -------------------------------------------


def search_candidates(query: str, limit: int = 20, cc_only: bool = True) -> List[Dict]:
    """Returns flat YouTube search results, cheapest metadata pass first."""
    yt_dlp = _import_yt_dlp()

    if cc_only:
        target = (
            "https://www.youtube.com/results?"
            f"search_query={urllib.parse.quote(query)}&sp={_CC_SEARCH_FILTER}"
        )
    else:
        target = f"ytsearch{limit}:{query}"

    opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "extract_flat": "in_playlist",
        "noplaylist": True,
        "playlist_items": f"1-{limit}",
    }

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(target, download=False) or {}
    except Exception as exc:
        print(f"[YouTubeBRoll] Search failed for '{query}' ({exc}).")
        return []

    return [e for e in (info.get("entries") or []) if e and e.get("id")]


def _prefilter(entry: Dict, min_duration: float, max_duration: float) -> bool:
    """Cheap rejects that avoid a full metadata fetch."""
    if entry.get("live_status") in ("is_live", "is_upcoming"):
        return False
    duration = entry.get("duration")
    if duration is None:
        return True  # unknown at this depth; let the detail pass decide
    return min_duration <= duration <= max_duration


def _fetch_details(video_id: str) -> Optional[Dict]:
    yt_dlp = _import_yt_dlp()
    opts = {"quiet": True, "no_warnings": True, "skip_download": True, "noplaylist": True}
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            return ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
    except Exception:
        return None


def _best_height(info: Dict) -> int:
    height = info.get("height") or 0
    if height:
        return height
    heights = [f.get("height") or 0 for f in info.get("formats") or []]
    return max(heights) if heights else 0


def _is_usable(info: Dict, clip_length: float, min_height: int, cc_only: bool) -> bool:
    if not info:
        return False
    if info.get("is_live") or info.get("live_status") in ("is_live", "is_upcoming"):
        return False
    if info.get("age_limit"):
        return False

    duration = info.get("duration") or 0
    if duration < clip_length + 4:
        return False

    height = _best_height(info)
    if height and height < min_height:
        return False

    if cc_only and _CC_LICENCE_MARKER not in (info.get("license") or "").lower():
        return False

    return True


def _score(info: Dict) -> float:
    """Ranks candidates: resolution first, then reach, then a sane length."""
    views = info.get("view_count") or 0
    duration = info.get("duration") or 0

    score = min(_best_height(info), 2160) / 100.0
    score += min(views, 5_000_000) / 500_000.0
    if 30 <= duration <= 900:
        score += 5.0
    return score


# --- Segment selection ------------------------------------------------------


def _probe_window(source_duration: float, clip_length: float, query: str) -> Tuple[float, float]:
    """Chooses which slice of the source video is worth downloading.

    Trims the intro and outro (talking heads, sponsor reads, end cards) and
    offsets deterministically by query, so several scenes drawing on the same
    video do not all land on identical footage.
    """
    head = max(3.0, source_duration * 0.12)
    tail = max(3.0, source_duration * 0.08)
    usable = source_duration - head - tail

    if usable < clip_length:
        head = max(0.0, (source_duration - clip_length) / 2)
        return head, min(clip_length, source_duration)

    probe_factor = _env_float("YOUTUBE_BROLL_PROBE_FACTOR", 5.0)
    max_probe = _env_float("YOUTUBE_BROLL_MAX_PROBE_SECONDS", 90.0)
    probe_length = max(clip_length, min(usable, clip_length * probe_factor, max_probe))

    digest = hashlib.sha1(query.encode("utf-8")).digest()[0] / 255.0
    start = head + (usable - probe_length) * digest
    return start, probe_length


def _detect_scene_cuts(video_path: Path) -> List[float]:
    """Returns timestamps of hard cuts inside a clip, via FFmpeg scene scores."""
    threshold = _env_float("YOUTUBE_BROLL_SCENE_THRESHOLD", 0.30)
    select_expr = f"select='gt(scene,{threshold})',metadata=print:file=-"
    cmd = [
        "ffmpeg", "-hide_banner", "-nostats",
        "-i", str(video_path),
        "-an", "-sn",
        "-filter:v", select_expr,
        "-f", "null", "-",
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    except (subprocess.SubprocessError, OSError):
        return []

    stream = f"{res.stdout}\n{res.stderr}"
    return sorted({float(t) for t in re.findall(r"pts_time:([0-9.]+)", stream)})


def _media_duration(video_path: Path) -> float:
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(video_path),
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return float(res.stdout.strip())
    except (subprocess.SubprocessError, OSError, ValueError):
        return 0.0


def _pick_longest_shot(cuts: List[float], duration: float, clip_length: float) -> float:
    """Returns the offset of the longest uninterrupted shot in the window.

    Continuous footage cuts better under narration than a segment that happens
    to straddle an edit, so the longest gap between detected cuts wins.
    """
    if duration <= clip_length:
        return 0.0

    boundaries = [0.0] + [c for c in cuts if 0.0 < c < duration] + [duration]
    best_start, best_length = 0.0, 0.0
    for start, end in zip(boundaries, boundaries[1:]):
        if end - start > best_length:
            best_start, best_length = start, end - start

    if best_length < clip_length:
        return max(0.0, (duration - clip_length) / 2)

    # Centre the cut inside the shot, away from the edits at either edge.
    return min(best_start + (best_length - clip_length) / 2, duration - clip_length)


# --- Download & normalise ---------------------------------------------------


def _download_probe(video_id: str, start: float, length: float, dest: Path, min_height: int) -> bool:
    yt_dlp = _import_yt_dlp()
    from yt_dlp.utils import download_range_func

    # Cap the source resolution. Left uncapped, yt-dlp happily pulls a 4K VP9
    # stream to make a 1080-wide clip, which costs minutes and hundreds of MB.
    max_height = max(min_height, _env_int("YOUTUBE_BROLL_MAX_HEIGHT", 1440))
    bounded = f"[height>={min_height}][height<={max_height}]"

    opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "overwrites": True,
        # Video-only: b-roll is muted under narration, and skipping the audio
        # stream keeps the download small and the licensing surface narrow.
        # H.264 first — it seeks faster than VP9 and cuts without a full decode.
        "format": (
            f"bv*[vcodec^=avc1]{bounded}/bv*{bounded}/"
            f"bv*[height>={min_height}]/bv*/b"
        ),
        "outtmpl": f"{dest.with_suffix('')}.%(ext)s",
        "merge_output_format": "mp4",
        "download_ranges": download_range_func(None, [(start, start + length)]),
        # No force_keyframes_at_cuts: _normalise_clip re-encodes the segment
        # anyway, so paying for a second re-encode here buys nothing.
        "force_keyframes_at_cuts": False,
    }

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([f"https://www.youtube.com/watch?v={video_id}"])
    except Exception as exc:
        print(f"[YouTubeBRoll] Segment download failed for {video_id} ({exc}).")
        return False

    if dest.exists() and dest.stat().st_size > 10_000:
        return True

    # yt-dlp may land on a different container than the template implies.
    for sibling in dest.parent.glob(f"{dest.stem}.*"):
        if sibling.suffix.lower() in (".mp4", ".mkv", ".webm") and sibling.stat().st_size > 10_000:
            sibling.replace(dest)
            return True
    return False


def _normalise_clip(source: Path, dest: Path, offset: float, length: float) -> bool:
    width, height = _target_resolution()
    fps = _env_int("YOUTUBE_BROLL_FPS", 30)
    vf = (
        f"scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height},setsar=1,fps={fps}"
    )
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-nostats", "-loglevel", "error",
        "-ss", f"{offset:.3f}",
        "-t", f"{length:.3f}",
        "-i", str(source),
        "-an",
        "-vf", vf,
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-pix_fmt", "yuv420p",
        str(dest),
    ]
    try:
        subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=300)
    except subprocess.CalledProcessError as exc:
        print(f"[YouTubeBRoll] Normalisation failed: {(exc.stderr or '')[-400:]}")
        return False
    except (subprocess.SubprocessError, OSError) as exc:
        print(f"[YouTubeBRoll] Normalisation failed ({exc}).")
        return False

    return dest.exists() and dest.stat().st_size > 10_000


# --- Attribution ledger -----------------------------------------------------


def _load_ledger() -> Dict[str, Dict]:
    if not LEDGER_FILE.exists():
        return {}
    try:
        with open(LEDGER_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def _record_attribution(clip: BRollClip) -> None:
    ledger = _load_ledger()
    ledger[Path(clip.path).name] = asdict(clip)

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with open(LEDGER_FILE, "w", encoding="utf-8") as f:
        json.dump(ledger, f, indent=2, ensure_ascii=False)

    _write_attribution_markdown(ledger)


def _write_attribution_markdown(ledger: Dict[str, Dict]) -> None:
    lines = [
        "# YouTube B-Roll Attribution",
        "",
        "Credits for every YouTube clip cached by `youtube_broll.py`. Creative",
        "Commons entries require this credit wherever the finished video is",
        "published; entries on the standard YouTube licence are not cleared for",
        "reuse and should be replaced before publishing.",
        "",
    ]

    for name, entry in sorted(ledger.items()):
        span = f"{entry.get('source_start', 0):.1f}s - {entry.get('source_end', 0):.1f}s"
        lines.extend([
            f"## {name}",
            "",
            f"- **Title:** {entry.get('title', 'unknown')}",
            f"- **Channel:** {entry.get('channel', 'unknown')} ({entry.get('channel_url', '')})",
            f"- **Source:** {entry.get('webpage_url', '')}",
            f"- **Licence:** {entry.get('license') or 'unknown'}",
            f"- **Segment used:** {span}",
            f"- **Matched query:** {entry.get('query', '')}",
            "",
        ])

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with open(LEDGER_MARKDOWN, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def attribution_report() -> str:
    """Returns the human-readable credit list for everything cached so far."""
    ledger = _load_ledger()
    if not ledger:
        return "No YouTube b-roll has been cached yet."

    blocks = []
    for name, entry in sorted(ledger.items()):
        blocks.append(
            f"{name}\n"
            f"  {entry.get('title', 'unknown')} - {entry.get('channel', 'unknown')}\n"
            f"  {entry.get('webpage_url', '')}\n"
            f"  {entry.get('license') or 'unknown licence'}"
        )
    return "\n\n".join(blocks)


# --- Public entry points ----------------------------------------------------


def _build_clip(
    path: Path, info: Dict, query: str, source_start: float, length: float, requested: float
) -> BRollClip:
    video_id = info.get("id", "")
    return BRollClip(
        path=str(path),
        video_id=video_id,
        title=info.get("title", ""),
        channel=info.get("channel") or info.get("uploader") or "",
        channel_url=info.get("channel_url") or info.get("uploader_url") or "",
        webpage_url=info.get("webpage_url") or f"https://www.youtube.com/watch?v={video_id}",
        license=info.get("license") or "",
        source_start=round(source_start, 2),
        source_end=round(source_start + length, 2),
        duration=round(length, 2),
        query=query,
        requested_duration=round(float(requested), 2),
    )


def _lookup_cached_clip(query: str, requested: float, excluded: set) -> Optional[BRollClip]:
    """Returns a previously cut clip for this exact request, if one survives.

    The per-video cache below can only be consulted once a search has named a
    video, and YouTube reorders results between runs — so without this pass a
    repeat request usually re-searches and re-downloads something new.
    """
    for entry in _load_ledger().values():
        if entry.get("query") != query:
            continue
        if round(float(entry.get("requested_duration") or 0), 2) != round(float(requested), 2):
            continue
        if entry.get("video_id") in excluded:
            continue

        path = Path(entry.get("path", ""))
        if not path.exists() or path.stat().st_size <= 10_000:
            continue

        try:
            return BRollClip(**entry)
        except TypeError:
            continue  # ledger written by an older schema; re-cut instead
    return None


def fetch_broll_clip(
    query: str,
    target_duration: float = 5.0,
    license_policy: Optional[str] = None,
    exclude_video_ids: Optional[List[str]] = None,
) -> Optional[BRollClip]:
    """Sources one normalised b-roll clip for ``query``.

    Returns ``None`` when nothing usable is found; the caller is expected to
    fall through to its next media tier.
    """
    policy = (license_policy or os.getenv("YOUTUBE_BROLL_LICENSE", "cc")).strip().lower()
    cc_only = policy != "any"
    clip_length = max(1.0, float(target_duration))
    min_height = _env_int("YOUTUBE_BROLL_MIN_HEIGHT", 720)
    max_source = _env_float("YOUTUBE_BROLL_MAX_SOURCE_SECONDS", 1800.0)
    search_limit = _env_int("YOUTUBE_BROLL_SEARCH_LIMIT", 20)
    max_detail_checks = _env_int("YOUTUBE_BROLL_DETAIL_CHECKS", 6)
    excluded = set(exclude_video_ids or [])

    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    reused = _lookup_cached_clip(query, clip_length, excluded)
    if reused:
        print(f"[YouTubeBRoll] Reusing cached b-roll for '{query}': {Path(reused.path).name}")
        return reused

    entries = search_candidates(query, limit=search_limit, cc_only=cc_only)
    if not entries:
        print(f"[YouTubeBRoll] No search results for '{query}'.")
        return None

    shortlist = [
        e for e in entries
        if e["id"] not in excluded and _prefilter(e, clip_length + 4, max_source)
    ]

    checked = []
    for entry in shortlist[:max_detail_checks]:
        info = _fetch_details(entry["id"])
        if _is_usable(info, clip_length, min_height, cc_only):
            checked.append(info)

    if not checked:
        print(f"[YouTubeBRoll] No usable candidate for '{query}' (licence policy: {policy}).")
        return None

    checked.sort(key=_score, reverse=True)

    for info in checked:
        video_id = info["id"]
        source_duration = float(info.get("duration") or 0)
        probe_start, probe_length = _probe_window(source_duration, clip_length, query)

        cache_path = CACHE_DIR / f"yt_{video_id}_{int(probe_start)}_{int(clip_length)}.mp4"
        probe_path = CACHE_DIR / f".probe_{video_id}_{int(probe_start)}.mp4"

        if cache_path.exists() and cache_path.stat().st_size > 10_000:
            print(f"[YouTubeBRoll] Cache hit for '{query}': {cache_path.name}")
            clip = _build_clip(cache_path, info, query, probe_start, clip_length, clip_length)
            _record_attribution(clip)
            return clip

        print(
            f"[YouTubeBRoll] '{query}' -> {info.get('title', video_id)[:60]} "
            f"[{info.get('license') or 'standard licence'}]"
        )
        if not _download_probe(video_id, probe_start, probe_length, probe_path, min_height):
            continue

        actual_probe = _media_duration(probe_path) or probe_length
        cuts = _detect_scene_cuts(probe_path)
        offset = _pick_longest_shot(cuts, actual_probe, clip_length)
        usable_length = min(clip_length, max(1.0, actual_probe - offset))

        rendered = _normalise_clip(probe_path, cache_path, offset, usable_length)
        probe_path.unlink(missing_ok=True)
        if not rendered:
            continue

        clip = _build_clip(
            cache_path, info, query, probe_start + offset, usable_length, clip_length
        )
        _record_attribution(clip)
        print(f"[YouTubeBRoll] Cut {usable_length:.1f}s of b-roll -> {cache_path.name}")
        return clip

    print(f"[YouTubeBRoll] Every candidate for '{query}' failed to download.")
    return None


def fetch_youtube_broll(
    query: str,
    target_duration: float = 5.0,
    license_policy: Optional[str] = None,
) -> Optional[str]:
    """Path-only wrapper matching the signature the media sourcers expect."""
    try:
        clip = fetch_broll_clip(query, target_duration, license_policy)
    except YouTubeBRollError as exc:
        print(f"[YouTubeBRoll] {exc}")
        return None
    return clip.path if clip else None


def main() -> int:
    parser = argparse.ArgumentParser(description="YouTube b-roll pipeline for VideoAI")
    parser.add_argument("--query", type=str, help="Scene keywords to source b-roll for")
    parser.add_argument("--duration", type=float, default=5.0, help="Clip length in seconds")
    parser.add_argument("--count", type=int, default=1, help="Number of distinct clips to fetch")
    parser.add_argument(
        "--license",
        dest="license_policy",
        choices=["cc", "any"],
        help="cc = Creative Commons only (default); any = ignore licence, rights are yours to clear",
    )
    parser.add_argument("--attribution", action="store_true", help="Print the credit ledger and exit")
    args = parser.parse_args()

    if args.attribution:
        print(attribution_report())
        return 0

    if not args.query:
        parser.error("--query is required unless --attribution is given")

    seen: List[str] = []
    for i in range(args.count):
        clip = fetch_broll_clip(
            args.query,
            target_duration=args.duration,
            license_policy=args.license_policy,
            exclude_video_ids=seen,
        )
        if not clip:
            print(f"[YouTubeBRoll] Stopped after {i} clip(s).")
            return 1 if i == 0 else 0
        seen.append(clip.video_id)
        print(f"  [{i + 1}/{args.count}] {clip.path}")
        print(f"        {clip.title} - {clip.channel}")
        print(f"        {clip.license or 'standard licence'}")

    print(f"\nCredits written to {LEDGER_MARKDOWN}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
