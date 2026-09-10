"""Gaming Fight & Character Clip Finder for VideoAI.

Search, filter, and automatically extract fight scenes, boss encounters, and character moments
from your indexed gaming video collection.
"""

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from dotenv import load_dotenv

from universal_gaming_scanner import get_global_index, scan_gaming_video

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", str(PROJECT_ROOT / "output")))
HIGHLIGHTS_DIR = OUTPUT_DIR / "highlights"

os.makedirs(HIGHLIGHTS_DIR, exist_ok=True)


def search_clips(
    character: Optional[str] = None,
    franchise: Optional[str] = None,
    game: Optional[str] = None,
    boss_only: bool = False,
    action_only: bool = False,
    min_intensity: float = 0.0
) -> List[Dict[str, Any]]:
    """Searches the global index for matching fight/character segments."""
    index = get_global_index()
    matched_results = []

    for v_path, data in index.items():
        # Check video-level filters
        if franchise:
            if not any(franchise.lower() in f.lower() for f in data.get("franchises", [])):
                continue

        if game:
            if not any(game.lower() in g.lower() for g in data.get("all_games", [])):
                continue

        if boss_only and not data.get("has_boss_fight", False):
            continue

        for seg in data.get("fight_segments", []):
            if boss_only and not seg.get("is_boss_fight", False):
                continue

            if min_intensity > 0 and seg.get("average_intensity", 0.0) < min_intensity:
                continue

            # Character match filter
            if character:
                char_lower = character.lower()
                chars_in_seg = [c.lower() for c in seg.get("characters", [])]
                bosses_in_seg = [b.lower() for b in seg.get("boss_names", [])]
                all_names = chars_in_seg + bosses_in_seg
                if not any(char_lower in name for name in all_names):
                    continue

            matched_results.append({
                "video_path": v_path,
                "filename": data.get("filename"),
                "game": data.get("primary_game"),
                "start_time": seg["start_time"],
                "end_time": seg["end_time"],
                "duration": seg["duration"],
                "is_boss_fight": seg["is_boss_fight"],
                "boss_names": seg.get("boss_names", []),
                "characters": seg.get("characters", []),
                "scene_types": seg.get("scene_types", []),
                "intensity": seg.get("average_intensity", 7.0),
                "summary": seg.get("highlight_summary", "")
            })

    return matched_results


def extract_clip(video_path: str, start_sec: float, end_sec: float, output_name: str) -> str:
    """Extracts a high-quality video subclip using FFmpeg fast accurate seek."""
    out_path = str(HIGHLIGHTS_DIR / output_name)
    duration = end_sec - start_sec

    cmd = [
        "ffmpeg", "-y",
        "-ss", str(start_sec),
        "-i", video_path,
        "-t", str(duration),
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "19",
        "-c:a", "aac",
        "-b:a", "192k",
        out_path
    ]

    try:
        subprocess.run(cmd, check=True, capture_output=True)
        return out_path
    except subprocess.CalledProcessError as e:
        stderr = e.stderr.decode("utf-8", errors="replace")[-400:] if e.stderr else ""
        print(f"[Extractor] Error cutting clip: {stderr}")
        return ""


def batch_scan_directory(dir_path: str, interval: float = 2.0):
    """Scans all video files in a folder recursively."""
    target_dir = Path(dir_path)
    if not target_dir.exists():
        print(f"Error: Directory not found: {dir_path}")
        return

    patterns = ["*.mp4", "*.mkv", "*.mov"]
    video_files = []
    for p in patterns:
        video_files.extend(list(target_dir.rglob(p)))

    print(f"\n=======================================================")
    print(f"   BATCH SCANNING GAMING DIRECTORY: {target_dir}")
    print(f"   Found {len(video_files)} video file(s) to process")
    print(f"=======================================================\n")

    for idx, vfile in enumerate(video_files):
        print(f"\n--- [{idx+1}/{len(video_files)}] Processing: {vfile.name} ---")
        try:
            scan_gaming_video(str(vfile), interval_seconds=interval)
        except Exception as err:
            print(f"[!] Scan error on {vfile.name}: {err}")


def print_results_table(results: List[Dict[str, Any]]):
    """Formats and prints search results in a clean terminal table."""
    if not results:
        print("\n[!] No matching fight or character clips found with specified filters.")
        return

    print(f"\n=========================================================================================================")
    print(f"   FOUND {len(results)} MATCHING FIGHT / ACTION SCENE(S)")
    print(f"=========================================================================================================")
    print(f"{'#':<3} | {'Game':<24} | {'Segment':<13} | {'Type':<16} | {'Intensity':<9} | {'Characters / Bosses'}")
    print(f"{'-'*3}-+-{'-'*24}-+-{'-'*13}-+-{'-'*16}-+-{'-'*9}-+-{'-'*35}")

    for idx, res in enumerate(results):
        t_str = f"{res['start_time']}s - {res['end_time']}s"
        stype = res["scene_types"][0] if res["scene_types"] else "Combat"
        if res["is_boss_fight"]:
            stype = f"[BOSS] {stype}"
        stype = stype[:16]
        game_str = res["game"][:24]

        chars = ", ".join(res["characters"])
        if res["boss_names"]:
            chars = f"Boss: {', '.join(res['boss_names'])} | {chars}"
        chars = chars[:45]

        print(f"{idx+1:<3} | {game_str:<24} | {t_str:<13} | {stype:<16} | {res['intensity']:<9.1f} | {chars}")

    print(f"=========================================================================================================\n")


def main():
    parser = argparse.ArgumentParser(description="Find and Extract Gaming Boss Fights & Character Action Clips")
    parser.add_argument("--character", type=str, help="Character name or alias (e.g. 'Batman', 'Robin', 'Bane', 'Kratos', 'Spider-Man')")
    parser.add_argument("--franchise", type=str, help="Franchise filter (e.g. 'DC', 'Marvel', 'God of War', 'GTA', 'Star Wars')")
    parser.add_argument("--game", type=str, help="Game title filter (e.g. 'Arkham Knight', 'Spider-Man 2', 'Ragnarok')")
    parser.add_argument("--boss-fights-only", action="store_true", help="Filter strictly for boss encounters")
    parser.add_argument("--action-only", action="store_true", help="Filter for active combat scenes")
    parser.add_argument("--min-intensity", type=float, default=0.0, help="Minimum intensity threshold (1.0 - 10.0)")
    parser.add_argument("--scan-file", type=str, help="Scan a single video file")
    parser.add_argument("--scan-dir", type=str, help="Scan an entire directory of gaming videos recursively")
    parser.add_argument("--interval", type=float, default=2.0, help="Sampling interval in seconds for scanner")
    parser.add_argument("--extract", action="store_true", help="Extract matched fight clips into output/highlights/")
    parser.add_argument("--json", action="store_true", help="Output results as JSON")

    args = parser.parse_args()

    # If scan requested
    if args.scan_file:
        scan_gaming_video(args.scan_file, interval_seconds=args.interval)
        return

    if args.scan_dir:
        batch_scan_directory(args.scan_dir, interval=args.interval)
        return

    # Perform search
    results = search_clips(
        character=args.character,
        franchise=args.franchise,
        game=args.game,
        boss_only=args.boss_fights_only,
        action_only=args.action_only,
        min_intensity=args.min_intensity
    )

    if args.json:
        print(json.dumps(results, indent=2))
        return

    print_results_table(results)

    # If extract requested
    if args.extract and results:
        print(f"[*] Extracting {len(results)} highlight clip(s) to: {HIGHLIGHTS_DIR}")
        for idx, res in enumerate(results):
            char_tag = "_".join(res["characters"][:2]) if res["characters"] else "combat"
            clean_game = "".join(c for c in res["game"] if c.isalnum())[:12]
            out_name = f"Highlight_{clean_game}_{char_tag}_{res['start_time']}s_{res['end_time']}s.mp4"
            print(f"  [{idx+1}/{len(results)}] Exporting: {out_name}...")
            out_file = extract_clip(res["video_path"], res["start_time"], res["end_time"], out_name)
            if out_file:
                print(f"    -> Saved: {out_file}")
        print("\n[+] All highlight extractions complete!\n")


if __name__ == "__main__":
    main()
