import requests
import json
import os
from dotenv import load_dotenv

load_dotenv()
key = os.getenv('EPIDEMIC_SOUND_API_KEY')

url = "https://www.epidemicsound.com/json/search/tracks/"
headers = {
    'Authorization': f'Bearer {key}',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}
params = {'term': 'cinematic ambient', 'limit': 5}

r = requests.get(url, headers=headers, params=params)
data = r.json()
tracks = data.get('entities', {}).get('tracks', {})

for track_id, track_info in list(tracks.items())[:3]:
    print("----------------------------------------")
    print(f"TRACK: {track_info.get('title')} (ID: {track_id})")
    print("KEYS:", list(track_info.keys()))
    if 'stems' in track_info:
        print("STEMS:", track_info['stems'])
    if 'publicCommercialTrack' in track_info:
        print("PUBLIC TRACK:", track_info['publicCommercialTrack'])
    # Search for any URL fields in track_info
    urls = {k: v for k, v in track_info.items() if isinstance(v, str) and ('http' in v or '.mp3' in v or 'stream' in v)}
    print("AUDIO URLS:", urls)
