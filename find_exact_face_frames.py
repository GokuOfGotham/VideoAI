import glob
import os
import sys

import cv2

from video_scan_utils import DEFAULT_VIDEO, OUTPUT_DIR, frame_timestamp

INTERVAL = 0.5  # matches the frames written by strict_face_detection


def find_faces(video_path=DEFAULT_VIDEO):
    """Confirm faces in the strict-scan frames using Haar cascades.

    Tuned for recall over precision - loose parameters catch partial and
    profile faces, at the cost of some false positives.
    """
    stem = os.path.splitext(os.path.basename(video_path))[0]
    frames_dir = os.path.join(OUTPUT_DIR, f"frames_strict_{stem}")
    files = sorted(glob.glob(os.path.join(frames_dir, "frame_*.jpg")),
                   key=lambda p: frame_timestamp(p, INTERVAL))

    if not files:
        print(f"[!] No frames found in {frames_dir} - run strict_face_detection first.")
        return []

    face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    profile_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_profileface.xml")

    face_found = []

    for f in files:
        sec = frame_timestamp(f, INTERVAL)
        img = cv2.imread(f)
        if img is None:
            continue

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        frontal = face_cascade.detectMultiScale(gray, scaleFactor=1.05, minNeighbors=3)
        profile = profile_cascade.detectMultiScale(gray, scaleFactor=1.05, minNeighbors=3)

        if len(frontal) > 0 or len(profile) > 0:
            face_found.append(sec)

    print(f"[!] CONFIRMED FACE TIMESTAMPS (sec): {face_found}")
    return face_found


if __name__ == "__main__":
    find_faces(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_VIDEO)
