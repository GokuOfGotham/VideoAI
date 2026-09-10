import os, subprocess

video = r'M:\Videos\Gaming\PlayStation 5\Batman Arkham Knight\Batman_ Arkham Knight (The Movie).mp4'
temp_dir = 'A:/ai/VideoAI/temp_frames_search'
os.makedirs(temp_dir, exist_ok=True)

# In Arkham Knight, the major Ace Chemicals courtyard/loading dock fight happens around 25m - 35m (1500s - 2100s)
# Let's extract 1 frame every 10 seconds from 1600s to 2000s
for sec in range(1600, 2000, 20):
    fpath = os.path.join(temp_dir, f"f_{sec}.jpg")
    cmd = ["ffmpeg", "-y", "-ss", str(sec), "-i", video, "-vframes", "1", "-vf", "scale=480:-2", "-q:v", "4", fpath]
    subprocess.run(cmd, capture_output=True)

print(f"Extracted {len(os.listdir(temp_dir))} test frames from 1600s to 2000s.")
