import os, cv2, numpy as np, subprocess

video = r'M:\Videos\Gaming\PlayStation 5\Batman Arkham Knight\Batman_ Arkham Knight (The Movie).mp4'
temp_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'inspect_hits')
os.makedirs(temp_dir, exist_ok=True)

# Extract 60 seconds of raw video from 00:36:00 to 00:37:00
print("[*] Extracting 60s raw segment from 4K Movie...")
raw_clip = os.path.join(temp_dir, 'raw_segment.mp4')
cmd = ['ffmpeg', '-y', '-ss', '00:36:00', '-i', video, '-t', '60.0', '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '22', '-c:a', 'copy', raw_clip]
subprocess.run(cmd, capture_output=True)

# Analyze audio volume spikes and video motion peaks to find the exact punch impacts!
cap = cv2.VideoCapture(raw_clip)
fps = cap.get(cv2.CAP_PROP_FPS)
total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
print(f"Total Frames: {total_frames} | FPS: {fps}")

prev_frame = None
motion_scores = []

while True:
    ret, frame = cap.read()
    if not ret:
        break
    gray = cv2.cvtColor(cv2.resize(frame, (320, 180)), cv2.COLOR_BGR2GRAY)
    if prev_frame is not None:
        diff = np.mean(cv2.absdiff(gray, prev_frame))
        motion_scores.append(diff)
    else:
        motion_scores.append(0.0)
    prev_frame = gray

cap.release()

# Find peak punch moments (local maxima in motion/flash)
peaks = []
for i in range(15, len(motion_scores)-15, 10):
    window = motion_scores[i-10:i+10]
    if motion_scores[i] == max(window) and motion_scores[i] > 12.0:
        sec = round(i / fps, 2)
        peaks.append((sec, round(motion_scores[i], 1)))

print("\nDetected Peak Impact / Punch Moments in this 60s Scene:")
for sec, score in peaks[:10]:
    print(f"  -> t={sec:05.2f}s (Impact Peak: {score})")
