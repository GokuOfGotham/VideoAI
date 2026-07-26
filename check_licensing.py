import requests
import json
import os
from dotenv import load_dotenv

load_dotenv()
key = os.getenv('EPIDEMIC_SOUND_API_KEY')

print(f"Checking Epidemic Sound Account & Licensing for key: {key[:20]}...")

headers = {
    'Authorization': f'Bearer {key}',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

endpoints = [
    "https://www.epidemicsound.com/json/me/",
    "https://www.epidemicsound.com/json/user/",
    "https://www.epidemicsound.com/json/subscriptions/",
    "https://www.epidemicsound.com/json/channels/",
    "https://www.epidemicsound.com/json/account/"
]

for url in endpoints:
    try:
        r = requests.get(url, headers=headers, timeout=5)
        print(f"URL: {url} -> Status: {r.status_code}")
        if r.status_code == 200:
            try:
                data = r.json()
                print("DATA PREVIEW:", json.dumps(data, indent=2)[:500])
            except Exception as e:
                print("Text Preview:", r.text[:200])
    except Exception as e:
        print(f"Failed {url}: {e}")
