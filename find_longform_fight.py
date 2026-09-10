import os, subprocess, httpx, base64, json
from dotenv import load_dotenv

load_dotenv()
google_key = os.getenv('GOOGLE_API_KEY')

video = r'M:\Videos\Gaming\PlayStation 5\Batman Arkham Knight\Batman_ Arkham Knight (The Movie).mp4'
temp_dir = os.path.join(PROJECT_ROOT, "temp_4k_inspect")
os.makedirs(temp_dir, exist_ok=True)

# Test candidate timestamp ranges (in seconds):
# 1200s (20m - Ace Chemicals / Chinatown fight), 1800s (30m), 2400s (40m), 3600s (1h), 4800s (1h20m), 6000s (1h40m)
candidates = [600, 1200, 1800, 2400, 3000, 3600, 4200, 4800, 5400, 6000]

print("[*] Sampling candidate timestamps in 4K movie...")
for sec in candidates:
    out_frame = os.path.join(temp_dir, f"frame_{sec}.jpg")
    cmd = ["ffmpeg", "-y", "-ss", str(sec), "-i", video, "-vframes", "1", "-vf", "scale=720:-2", "-q:v", "3", out_frame]
    subprocess.run(cmd, capture_output=True)

print("[+] Frames extracted, running vision classification...")
with httpx.Client(timeout=30.0) as client:
    for sec in candidates:
        fpath = os.path.join(temp_dir, f"frame_{sec}.jpg")
        if not os.path.exists(fpath):
            continue
        with open(fpath, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("utf-8")
        prompt = "Is Batman in active physical hand-to-hand combat / brawl in this frame? Return JSON: {\"is_combat\": bool, \"scene\": string, \"intensity\": number}"
        payload = {
            "contents": [{"parts": [{"text": prompt}, {"inline_data": {"mime_type": "image/jpeg", "data": b64}}]}],
            "generationConfig": {"response_mime_type": "application/json"}
        }
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={google_key}"
        res = client.post(url, json=payload)
        if res.status_code == 200:
            data = json.loads(res.json()["candidates"][0]["content"]["parts"][0]["text"])
            mins = sec // 60
            print(f"  t={mins}m ({sec}s): Combat={data.get('is_combat')} | Intensity={data.get('intensity')} | {data.get('scene')}")

# cleanup
import shutil

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.getenv("OUTPUT_DIR", os.path.join(PROJECT_ROOT, "output"))
MUSIC_DIR = os.getenv("EPIDEMIC_MUSIC_DIR", os.path.join(PROJECT_ROOT, "assets", "epidemic_sound"))

shutil.rmtree(temp_dir, ignore_errors=True)
