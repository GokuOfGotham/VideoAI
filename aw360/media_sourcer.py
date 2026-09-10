"""
AW360 Animal World 360 - Budget-Optimized Media Sourcer & Veo 3.1 Director
Offers flexible modes to protect your Google API monthly spend cap:
  - 'stock' (Default, $0.00 API video cost): Uses free HD Pexels vertical videos,
    licence-filtered YouTube b-roll & public domain media.
  - 'hybrid': Uses free media first, with smart fallback to Veo 3.1 only when nothing free matched.
  - 'veo': Full Google Veo 3.1 AI Video generation.
"""

import os
import re
import time
import urllib.parse
import requests
from PIL import Image, ImageDraw, ImageFont
from dotenv import load_dotenv
from google import genai
from google.genai import types

from . import paths

load_dotenv()

PEXELS_API_KEY = os.getenv("PEXELS_API_KEY", "")

class MediaSourcer:
    def __init__(self, mode: str = "stock", cache_dir: str = None):
        self.mode = mode.lower()  # 'stock', 'hybrid', or 'veo'
        self.cache_dir = str(cache_dir or paths.CACHE_DIR)
        os.makedirs(self.cache_dir, exist_ok=True)
        self.google_api_key = os.getenv("GOOGLE_API_KEY")
        self.genai_client = genai.Client(api_key=self.google_api_key) if self.google_api_key else None
        self.last_veo_time = 0

    def fetch_scene_media(self, scene: dict, target_aspect="9:16") -> str:
        """
        Retrieves or generates media for a scene while strictly respecting budget mode.
        """
        scene_id = scene.get("scene_id", 1)
        search_query = scene.get("visual_search_query", "wild animal nature")
        ai_prompt = scene.get("ai_image_prompt", search_query)

        clean_name = re.sub(r'[^a-zA-Z0-9_]', '_', search_query[:30])
        veo_video_path = os.path.join(self.cache_dir, f"veo_scene_{scene_id}_{clean_name}.mp4")
        pexels_out = os.path.join(self.cache_dir, f"pexels_scene_{scene_id}_{clean_name}.mp4")
        procedural_out = os.path.join(self.cache_dir, f"procedural_scene_{scene_id}.jpg")

        # 1. Check local cache first (Free)
        if os.path.exists(veo_video_path) and os.path.getsize(veo_video_path) > 1000:
            return veo_video_path
        if os.path.exists(pexels_out) and os.path.getsize(pexels_out) > 1000:
            return pexels_out

        # 2. Mode 'veo': Generate Google Veo 3.1 AI Video directly
        if self.mode == "veo" and self.genai_client:
            veo_file = self._try_veo_generation(scene_id, ai_prompt, veo_video_path)
            if veo_file:
                return veo_file

        # 3. Mode 'stock' or 'hybrid': Search Pexels HD Stock Video ($0.00 cost)
        if PEXELS_API_KEY or self.mode in ["stock", "hybrid"]:
            video_url = self._search_pexels_video(search_query)
            if video_url and self._download_file(video_url, pexels_out):
                print(f"   [MediaSourcer] Downloaded HD Pexels Stock Video ($0.00 cost): {search_query}")
                return pexels_out

        # 4. YouTube b-roll, licence-filtered ($0.00 cost). Sits ahead of Veo so
        #    hybrid mode only spends on generation when nothing free matched.
        broll = self._fetch_youtube_broll(search_query, scene.get("duration_est", 6.0))
        if broll:
            print(f"   [MediaSourcer] Cut YouTube b-roll ($0.00 cost): {search_query}")
            return broll

        # 5. Mode 'hybrid': Fallback to Veo 3.1 if stock video not found
        if self.mode == "hybrid" and self.genai_client:
            veo_file = self._try_veo_generation(scene_id, ai_prompt, veo_video_path)
            if veo_file:
                return veo_file

        # 6. Public domain image search ($0.00 cost)
        pub_image = self._search_public_image(search_query)
        if pub_image:
            pub_out = os.path.join(self.cache_dir, f"pub_scene_{scene_id}_{clean_name}.jpg")
            if self._download_file(pub_image, pub_out):
                return pub_out

        # 7. Procedural visual card fallback ($0.00 cost)
        self._generate_procedural_scene_image(
            title="AW360 ANIMAL WORLD",
            subtitle=search_query.title(),
            description=scene.get("narration", "")[:100],
            output_path=procedural_out
        )
        return procedural_out

    def _fetch_youtube_broll(self, query: str, duration: float) -> str:
        """Cuts licence-filtered b-roll from YouTube, or None to fall through.

        Imported lazily so a missing yt-dlp downgrades this tier instead of
        breaking the whole director run. Honours YOUTUBE_BROLL_PRIORITY=off.
        """
        if os.getenv("YOUTUBE_BROLL_PRIORITY", "fallback").strip().lower() == "off":
            return None

        try:
            import sys
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            if project_root not in sys.path:
                sys.path.insert(0, project_root)
            from youtube_broll import fetch_youtube_broll
        except ImportError as e:
            print(f"   [MediaSourcer] YouTube b-roll tier unavailable ({e}).")
            return None

        return fetch_youtube_broll(query, target_duration=float(duration or 6.0))

    def _try_veo_generation(self, scene_id: int, prompt_text: str, dest_path: str) -> str:
        """Rate-limited call to Veo 3.1 Fast AI Video model."""
        elapsed = time.time() - self.last_veo_time
        if elapsed < 12:
            time.sleep(12 - elapsed)

        print(f"   [MediaSourcer] Generating Veo 3.1 AI Video for Scene {scene_id}...")
        self.last_veo_time = time.time()
        try:
            full_prompt = f"Cinematic 9:16 vertical video of {prompt_text}, high speed nature documentary, 4k ultra realistic"
            op = self.genai_client.models.generate_videos(
                model="veo-3.1-fast-generate-preview",
                source=types.GenerateVideosSource(prompt=full_prompt),
                config=types.GenerateVideosConfig(aspect_ratio="9:16")
            )
            for _ in range(20):
                if op.done:
                    break
                time.sleep(5)
                op = self.genai_client.operations.get(op)

            if op.done and op.result and op.result.generated_videos:
                video_obj = op.result.generated_videos[0].video
                if hasattr(video_obj, "uri") and video_obj.uri:
                    download_url = f"{video_obj.uri}&key={self.google_api_key}"
                    r = requests.get(download_url, timeout=30)
                    if r.status_code == 200:
                        with open(dest_path, "wb") as f:
                            f.write(r.content)
                        return dest_path
        except Exception as e:
            print(f"   [MediaSourcer] Veo generation note: {e}")
        return None

    def _search_pexels_video(self, query: str) -> str:
        try:
            url = f"https://api.pexels.com/videos/search?query={urllib.parse.quote(query)}&orientation=portrait&per_page=5"
            headers = {"Authorization": PEXELS_API_KEY} if PEXELS_API_KEY else {}
            resp = requests.get(url, headers=headers, timeout=10)
            if resp.status_code == 200:
                videos = resp.json().get("videos", [])
                if videos:
                    files = videos[0].get("video_files", [])
                    for vf in files:
                        if vf.get("width") and vf.get("height") and vf["height"] > vf["width"]:
                            return vf.get("link")
                    if files:
                        return files[0].get("link")
        except Exception:
            pass
        return None

    def _search_public_image(self, query: str) -> str:
        try:
            search_url = f"https://commons.wikimedia.org/w/api.php?action=query&generator=search&gsrsearch={urllib.parse.quote(query)}&gsrnamespace=6&gsrlimit=3&prop=imageinfo&iiprop=url&format=json"
            headers = {"User-Agent": "AW360Bot/1.0"}
            resp = requests.get(search_url, headers=headers, timeout=8)
            if resp.status_code == 200:
                pages = resp.json().get("query", {}).get("pages", {})
                for page in pages.values():
                    imageinfo = page.get("imageinfo", [])
                    if imageinfo:
                        img_url = imageinfo[0].get("url")
                        if img_url and any(img_url.lower().endswith(ext) for ext in ['.jpg', '.jpeg', '.png']):
                            return img_url
        except Exception:
            pass
        return None

    def _download_file(self, url: str, dest_path: str) -> bool:
        try:
            r = requests.get(url, timeout=20)
            if r.status_code == 200:
                with open(dest_path, "wb") as f:
                    f.write(r.content)
                return True
        except Exception:
            return False

    def _generate_procedural_scene_image(self, title: str, subtitle: str, description: str, output_path: str):
        w, h = 1080, 1920
        img = Image.new("RGB", (w, h), color=(12, 20, 28))
        draw = ImageDraw.Draw(img)
        draw.ellipse([-200, 300, 1280, 1500], fill=(24, 50, 70))
        draw.ellipse([100, 700, 980, 1400], fill=(18, 36, 50))

        try:
            font_title = ImageFont.truetype("arial.ttf", 64)
            font_sub = ImageFont.truetype("arialbd.ttf", 76)
            font_body = ImageFont.truetype("arial.ttf", 42)
        except:
            font_title = font_sub = font_body = ImageFont.load_default()

        draw.rectangle([140, 300, 940, 400], fill=(0, 180, 216), outline=(255, 255, 255), width=3)
        draw.text((540, 350), "AW360 ANIMAL WORLD 360", fill=(255, 255, 255), font=font_title, anchor="mm")
        draw.text((540, 960), subtitle.upper(), fill=(255, 215, 0), font=font_sub, anchor="mm")
        draw.rectangle([100, 1500, 980, 1750], fill=(0, 0, 0, 180), outline=(0, 180, 216), width=2)
        draw.text((540, 1625), "SUBSCRIBE FOR DAILY ANIMAL FACTS", fill=(255, 255, 255), font=font_body, anchor="mm")
        img.save(output_path, quality=95)
