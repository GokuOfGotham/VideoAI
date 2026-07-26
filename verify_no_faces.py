import glob
import os

import cv2

from video_scan_utils import OUTPUT_DIR, frame_timestamp, skin_ratio

INTERVAL = 2.0  # thumbnails are sampled every two seconds
THRESHOLD = 0.02


def check_thumbs():
    """Analyse the thumbnails produced by inspect_all_scenes.py."""
    thumbs_dir = os.path.join(OUTPUT_DIR, "scene_thumbs")
    files = sorted(glob.glob(os.path.join(thumbs_dir, "thumb_*.jpg")),
                   key=lambda p: frame_timestamp(p, INTERVAL))

    if not files:
        print(f"[!] No thumbnails found in {thumbs_dir} - run inspect_all_scenes.py first.")
        return []

    print("Thumbnail Detailed Skin/Face Color Analysis:")
    clean_seconds = []

    for f in files:
        sec = frame_timestamp(f, INTERVAL)
        img = cv2.imread(f)
        if img is None:
            continue

        ratio = skin_ratio(img)
        has_face = ratio > THRESHOLD
        print(f"  - {sec:g}s ({os.path.basename(f)}): skin_ratio={ratio:.4f}"
              f" -> {'FACE/HUMAN' if has_face else 'PURE AIRCRAFT'}")
        if not has_face:
            clean_seconds.append(sec)

    print(f"\n[+] Pure Aircraft Seconds (0% Faces): {clean_seconds}")
    return clean_seconds


if __name__ == "__main__":
    check_thumbs()
