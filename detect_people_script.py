import cv2
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

MEDIA_ROOT = os.getenv("MEDIA_ROOT", str(Path(__file__).resolve().parent / "media"))
MILITARY_VIDEOS_DIR = os.getenv("MILITARY_VIDEOS_DIR", os.path.join(MEDIA_ROOT, "US Military"))

def check_video(video_path):
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration = total_frames / fps
    print(f"[*] Analyzing video: {video_path} (Duration: {duration:.2f}s, FPS: {fps:.2f})")
    
    cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
    
    face_intervals = []
    current_start = None
    frame_idx = 0
    step = 10  # check every 10 frames (~0.16s)
    
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break
        frame_idx += 1
        
        if frame_idx % step == 0:
            sec = frame_idx / fps
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(60, 60))
            
            if len(faces) > 0:
                if current_start is None:
                    current_start = sec
            else:
                if current_start is not None:
                    face_intervals.append((round(current_start, 1), round(sec, 1)))
                    current_start = None
                    
    if current_start is not None:
        face_intervals.append((round(current_start, 1), round(duration, 1)))
        
    cap.release()
    print(f"[+] Detected People/Face intervals: {face_intervals}")
    return face_intervals

if __name__ == "__main__":
    check_video(os.path.join(MILITARY_VIDEOS_DIR, "DOD_111608478.mp4"))
