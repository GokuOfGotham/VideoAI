import cv2, numpy as np, os, subprocess

video = r'M:\Videos\Gaming\PlayStation 5\Batman Arkham Knight\Batman_ Arkham Knight (The Movie).mp4'
print("[*] Scanning 4K Movie for Highest-Intensity Continuous 60s Fight Scene using Motion Energy...")

# We sample every 30 seconds across the first 2 hours (0s to 7200s)
# For each candidate, we check 60 continuous seconds
best_score = 0.0
best_start = 0

candidates = [
    300, 600, 900, 1100, 1150, 1200, 1500, 1800, 2100, 2200, 2400, 
    2700, 3000, 3300, 3600, 4000, 4500, 4800, 5200, 5600, 6000, 6400, 6800, 7200
]

for sec in candidates:
    # Extract 5 sample frames across a 60-second window: t, t+15, t+30, t+45, t+60
    frames = []
    for offset in [0, 15, 30, 45, 60]:
        t_pos = sec + offset
        cmd = ["ffmpeg", "-y", "-ss", str(t_pos), "-i", video, "-vframes", "1", "-vf", "scale=320:180", "-q:v", "5", f"A:/ai/VideoAI/motion_{offset}.jpg"]
        subprocess.run(cmd, capture_output=True)
        img = cv2.imread(f"A:/ai/VideoAI/motion_{offset}.jpg", cv2.IMREAD_GRAYSCALE)
        if img is not None:
            frames.append(img)
        if os.path.exists(f"A:/ai/VideoAI/motion_{offset}.jpg"):
            os.remove(f"A:/ai/VideoAI/motion_{offset}.jpg")

    if len(frames) >= 4:
        diffs = [np.mean(cv2.absdiff(frames[i], frames[i+1])) for i in range(len(frames)-1)]
        score = sum(diffs) / len(diffs)
        mins = sec // 60
        r_sec = sec % 60
        print(f"  t={mins:02d}:{r_sec:02d} ({sec}s -> {sec+60}s) : Motion Score = {score:.2f}")
        if score > best_score:
            best_score = score
            best_start = sec

mins = best_start // 60
r_sec = best_start % 60
print(f"\n[+] PEAK CONTINUOUS ACTION SCENE: t={mins:02d}:{r_sec:02d} ({best_start}s to {best_start+60}s) with Score={best_score:.2f}")
