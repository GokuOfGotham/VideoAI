import os, httpx, json, re
from dotenv import load_dotenv

load_dotenv()
key = os.getenv('EPIDEMIC_SOUND_API_KEY')
sfx_dir = os.path.join(
    os.getenv('EPIDEMIC_MUSIC_DIR',
              os.path.join(os.path.dirname(os.path.abspath(__file__)), 'assets', 'epidemic_sound')),
    'sfx')
os.makedirs(sfx_dir, exist_ok=True)

url = 'https://www.epidemicsound.com/json/search/sfx/'
headers = {
    'Authorization': f'Bearer {key}',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
}

queries = ['punch face', 'punch bone crunch', 'punch heavy body impact', 'punch hit hard']
downloaded_sfx = []

for q in queries:
    r = httpx.get(url, headers=headers, params={'term': q, 'limit': 4}, timeout=15.0)
    if r.status_code == 200:
        tracks = r.json().get('entities', {}).get('tracks', {})
        for tid, t in tracks.items():
            mp3_url = t.get('stems', {}).get('full', {}).get('lqMp3Url')
            title = t.get('title', f'SFX_{tid}')
            if mp3_url:
                clean_title = re.sub(r'[^\w\-_]', '_', title)
                out_path = os.path.join(sfx_dir, f'{clean_title}.mp3')
                if not os.path.exists(out_path):
                    print(f'Downloading SFX: {title}...')
                    res = httpx.get(mp3_url, timeout=20.0)
                    with open(out_path, 'wb') as f:
                        f.write(res.content)
                else:
                    print(f'Cached SFX: {title}')
                downloaded_sfx.append((title, out_path))
                break

print('\nDownloaded Hollywood Punch SFX:')
for title, p in downloaded_sfx:
    print(f'  - {title} -> {p}')
