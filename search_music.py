import os
import requests
import json
from dotenv import load_dotenv

load_dotenv()
EPIDEMIC_SOUND_API_KEY = os.getenv('EPIDEMIC_SOUND_API_KEY')

def search_catalog(terms):
    url = "https://www.epidemicsound.com/json/search/tracks/"
    headers = {'Authorization': f'Bearer {EPIDEMIC_SOUND_API_KEY}'}
    
    print("\n=======================================================")
    print("      EPIDEMIC SOUND TOP-TIER ACTION TRACKS CATALOG    ")
    print("=======================================================")
    
    all_tracks = []
    for term in terms:
        params = {'term': term, 'limit': 8}
        res = requests.get(url, headers=headers, params=params).json()
        tracks_dict = res.get('entities', {}).get('tracks', {})
        for track_id, track in tracks_dict.items():
            stems = track.get('stems', {})
            full_stem = stems.get('full', {})
            mp3_url = full_stem.get('lqMp3Url')
            title = track.get('title', 'Unknown Track')
            creatives = track.get('creatives', {}).get('mainArtists', [])
            artist = creatives[0].get('name') if creatives else 'Epidemic Artist'
            if mp3_url:
                all_tracks.append({
                    'id': track_id,
                    'title': title,
                    'artist': artist,
                    'search_term': term,
                    'mp3_url': mp3_url
                })
                
    # Deduplicate by track title
    seen = set()
    unique_tracks = []
    for t in all_tracks:
        if t['title'] not in seen:
            seen.add(t['title'])
            unique_tracks.append(t)
            
    for i, t in enumerate(unique_tracks[:12]):
        print(f"[{i+1:2d}] \"{t['title']}\" — {t['artist']}  (Category: {t['search_term']})")
        
    return unique_tracks

if __name__ == "__main__":
    search_catalog([
        "epic hybrid action trailer",
        "explosive blockbuster action",
        "war cinematic trailer",
        "intense dark action drop"
    ])
