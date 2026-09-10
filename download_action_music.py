import os, httpx, json, re
from dotenv import load_dotenv

load_dotenv('A:/ai/VideoAI/.env')
key = os.getenv('EPIDEMIC_SOUND_API_KEY')
music_dir = 'A:/ai/VideoAI/assets/epidemic_sound'
os.makedirs(music_dir, exist_ok=True)

url = 'https://www.epidemicsound.com/json/search/tracks/'
headers = {
    'Authorization': f'Bearer {key}',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
}

queries = [
    'heavy metal action combat fight trailer',
    'epic superhero blockbuster fight trailer',
    'cyberpunk high octane combat drive'
]

downloaded = []
for q in queries:
    r = httpx.get(url, headers=headers, params={'term': q, 'limit': 8}, timeout=15.0)
    if r.status_code == 200:
        tracks = r.json().get('entities', {}).get('tracks', {})
        for tid, t in tracks.items():
            stems = t.get('stems', {})
            full_stem = stems.get('full', {})
            mp3_url = full_stem.get('lqMp3Url')
            title = t.get('title', 'Action')
            bpm = t.get('bpm')
            if mp3_url:
                clean_title = re.sub(r'[^\w\-_]', '_', title)
                out_file = os.path.join(music_dir, f'{clean_title}.mp3')
                if not os.path.exists(out_file):
                    print(f'Downloading {title} (BPM: {bpm}) for "{q}"...')
                    a_res = httpx.get(mp3_url, timeout=30.0)
                    with open(out_file, 'wb') as f:
                        f.write(a_res.content)
                else:
                    print(f'Cached: {title} (BPM: {bpm})')
                downloaded.append((title, bpm, out_file))
                break

print('\nReady Action Tracks:')
for title, bpm, path in downloaded:
    print(f'  - {title} (BPM: {bpm}) -> {path}')
