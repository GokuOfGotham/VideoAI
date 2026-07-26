import os
import sys

import cv2

from video_scan_utils import (
    DEFAULT_VIDEO,
    OUTPUT_DIR,
    SKIN_RATIO_THRESHOLD,
    extract_frames,
    frame_timestamp,
    skin_ratio,
)

INTERVAL = 0.5  # two frames per second


def strict_scan(video_path=DEFAULT_VIDEO, threshold=SKIN_RATIO_THRESHOLD):
    """Half-second scan with a deliberately low threshold to catch any face,
    helmet, or exposed skin."""
    stem = os.path.splitext(os.path.basename(video_path))[0]
    output_dir = os.path.join(OUTPUT_DIR, f"frames_strict_{stem}")

    print(f"[*] Extracting 0.5-second frames for {os.path.basename(video_path)}...")
    files = extract_frames(video_path, output_dir, fps_filter="2")

    face_seconds = []
    clean_seconds = []

    for f in files:
        sec = frame_timestamp(f, INTERVAL)
        img = cv2.imread(f)
        if img is None:
            continue

        if skin_ratio(img) > threshold:
            face_seconds.append(sec)
        else:
            clean_seconds.append(sec)

    print(f"[+] Total Clean 0.5s Intervals: {len(clean_seconds)}")
    print(f"[!] Face/Head/Skin detected timestamps (sec): {face_seconds}")
    print(f"Clean timeline seconds: {clean_seconds}")
    return clean_seconds


if __name__ == "__main__":
    strict_scan(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_VIDEO)
