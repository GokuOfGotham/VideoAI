"""
AW360 Animal World 360 - Audio Director & Music Mixer
Searches Epidemic Sound catalogue, downloads licensed background music,
and mixes background music under voiceover with audio ducking.
"""

import os
import requests
import subprocess
from dotenv import load_dotenv

from . import paths

load_dotenv()

EPIDEMIC_SOUND_API_KEY = os.getenv("EPIDEMIC_SOUND_API_KEY")

class AudioDirector:
    def __init__(self, music_dir: str = None, cache_dir: str = None):
        self.music_dir = str(music_dir or paths.EPIDEMIC_MUSIC_DIR)
        self.cache_dir = str(cache_dir or paths.CACHE_DIR)
        os.makedirs(self.music_dir, exist_ok=True)
        os.makedirs(self.cache_dir, exist_ok=True)

    def fetch_background_music(self, mood: str = "epic") -> str:
        """
        Searches Epidemic Sound for a track matching the mood and downloads it.
        Returns path to local .mp3 track file.
        """
        search_terms = {
            "epic": ["epic documentary orchestral", "nature documentary cinematic", "trailer epic action"],
            "suspenseful": ["dark tension thriller", "suspense documentary", "mysterious ocean"],
            "energetic": ["upbeat action nature", "fast rhythmic trailer", "adventure fast"],
            "awe": ["majestic ambient nature", "breathtaking documentary", "wondrous atmosphere"]
        }

        terms = search_terms.get(mood.lower(), search_terms["epic"])

        if EPIDEMIC_SOUND_API_KEY:
            track_file = self._search_and_download_epidemic(terms)
            if track_file and os.path.exists(track_file):
                return track_file

        # Check if any .mp3 exists in music_dir
        existing_mp3s = [os.path.join(self.music_dir, f) for f in os.listdir(self.music_dir) if f.endswith(".mp3")]
        if existing_mp3s:
            return existing_mp3s[0]

        # Generate procedural ambient drone if no track available
        fallback_path = os.path.join(self.cache_dir, "ambient_fallback.mp3")
        self._generate_fallback_ambient(fallback_path)
        return fallback_path

    def _search_and_download_epidemic(self, terms: list) -> str:
        url = "https://www.epidemicsound.com/json/search/tracks/"
        headers = {'Authorization': f'Bearer {EPIDEMIC_SOUND_API_KEY}'}

        for term in terms:
            try:
                params = {'term': term, 'limit': 5}
                res = requests.get(url, headers=headers, params=params, timeout=10)
                if res.status_code == 200:
                    data = res.json()
                    tracks_dict = data.get('entities', {}).get('tracks', {})
                    for track_id, track in tracks_dict.items():
                        title = track.get('title', f'track_{track_id}').replace(" ", "_")
                        stems = track.get('stems', {})
                        full_stem = stems.get('full', {})
                        mp3_url = full_stem.get('lqMp3Url') or full_stem.get('mp3Url')
                        if mp3_url:
                            dest_path = os.path.join(self.music_dir, f"epidemic_{title}.mp3")
                            if os.path.exists(dest_path):
                                return dest_path
                            r = requests.get(mp3_url, timeout=15)
                            if r.status_code == 200:
                                with open(dest_path, "wb") as f:
                                    f.write(r.content)
                                print(f"[AudioDirector] Downloaded Epidemic Track: {title}")
                                return dest_path
            except Exception as e:
                print(f"[AudioDirector] Epidemic search error for term '{term}': {e}")
        return None

    def _generate_fallback_ambient(self, dest_path: str, duration: float = 60.0):
        """Creates a subtle ambient drone using FFmpeg synth filter as fallback."""
        try:
            cmd = [
                "ffmpeg", "-y",
                "-f", "lavfi", "-i", f"sine=frequency=110:sample_rate=44100:duration={duration}",
                "-af", "volume=0.08,lowpass=f=400",
                dest_path
            ]
            subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        except Exception as e:
            print(f"[AudioDirector] Fallback synth generation error: {e}")

    def mix_narration_and_music(self, voiceover_path: str, music_path: str, output_path: str, total_duration: float) -> str:
        """
        Combines voiceover (volume 1.0) with background music (volume 0.12 - 0.15),
        looping music if needed and adding fade-in/fade-out.
        """
        try:
            filter_complex = (
                f"[1:a]aloop=loop=-1:size=2e+09,atrim=0:{total_duration},"
                f"volume=0.14,afade=t=in:st=0:d=1.5,afade=t=out:st={max(0, total_duration - 2)}:d=2[music];"
                f"[0:a][music]amix=inputs=2:duration=first:dropout_transition=2[outa]"
            )
            cmd = [
                "ffmpeg", "-y",
                "-i", voiceover_path,
                "-i", music_path,
                "-filter_complex", filter_complex,
                "-map", "[outa]",
                "-c:a", "aac", "-b:a", "192k",
                output_path
            ]
            subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
            return output_path
        except Exception as e:
            print(f"[AudioDirector] Audio mix error: {e}")
            return voiceover_path

if __name__ == "__main__":
    ad = AudioDirector()
    track = ad.fetch_background_music("epic")
    print(f"Background Music Track: {track}")
