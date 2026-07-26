import cv2
import glob
import os
import numpy as np
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

OUTPUT_DIR = os.getenv("OUTPUT_DIR", str(Path(__file__).resolve().parent / "output"))

def scan_frames():
    files = sorted(glob.glob(os.path.join(OUTPUT_DIR, "b2_frame_*.jpg")))
    print(f"Scanned {len(files)} frame thumbnails:")
    
    for f in files:
        img = cv2.imread(f)
        if img is None:
            continue
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        # Skin tone range in HSV
        lower_skin = np.array([0, 20, 70], dtype=np.uint8)
        upper_skin = np.array([20, 255, 255], dtype=np.uint8)
        mask = cv2.inRange(hsv, lower_skin, upper_skin)
        skin_ratio = np.sum(mask > 0) / (img.shape[0] * img.shape[1])
        print(f"  - {f}: skin_ratio={skin_ratio:.4f}")

if __name__ == "__main__":
    scan_frames()
