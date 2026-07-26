import os
import sys

import cv2

from video_scan_utils import (
    DEFAULT_VIDEO,
    OUTPUT_DIR,
    extract_frames,
    frame_timestamp,
    skin_ratio,
)

INTERVAL = 1.0  # one frame per second


def analyze_video(video_path=DEFAULT_VIDEO, threshold=0.08):
    output_dir = os.path.join(OUTPUT_DIR, "frames_" + os.path.splitext(os.path.basename(video_path))[0])

    print(f"[*] Extracting 1-second frames for {os.path.basename(video_path)}...")
    files = extract_frames(video_path, output_dir, fps_filter="1")

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

    print(f"[+] Total Clean Seconds (0% Faces/Skin): {len(clean_seconds)} sec")
    print(f"[!] Human face/skin detected seconds: {face_seconds}")
    print(f"Clean timeline seconds: {clean_seconds}")
    return clean_seconds


if __name__ == "__main__":
    analyze_video(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_VIDEO)
