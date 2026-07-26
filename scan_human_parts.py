import cv2
import glob
import os
import numpy as np
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

OUTPUT_DIR = os.getenv("OUTPUT_DIR", str(Path(__file__).resolve().parent / "output"))

def analyze_all_seconds():
    files = sorted(glob.glob(os.path.join(OUTPUT_DIR, "b2_sec_frames", "sec_*.jpg")))
    
    clean_seconds = []
    human_seconds = []
    
    for f in files:
        sec = int(os.path.basename(f).replace("sec_", "").replace(".jpg", ""))
        img = cv2.imread(f)
        if img is None:
            continue
            
        b, g, r = img[:,:,0], img[:,:,1], img[:,:,2]
        
        # Skin color heuristic in BGR
        skin_mask = (r > 95) & (g > 40) & (b > 20) & \
                    ((np.maximum(r, np.maximum(g, b)) - np.minimum(r, np.minimum(g, b))) > 15) & \
                    (abs(r.astype(int) - g.astype(int)) > 15) & (r > g) & (r > b)
                    
        skin_ratio = np.sum(skin_mask) / (img.shape[0] * img.shape[1])
        
        if skin_ratio > 0.08:
            human_seconds.append(sec)
        else:
            clean_seconds.append(sec)
            
    print(f"[+] Total Clean Seconds (Pure B-2 Aircraft Only): {len(clean_seconds)} sec")
    print(f"[!] Human/Skin-detected Seconds: {human_seconds}")
    print(f"Clean timeline seconds list: {clean_seconds}")

if __name__ == "__main__":
    analyze_all_seconds()


