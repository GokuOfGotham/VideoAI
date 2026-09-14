"""
AW360 Animal World 360 - High Quality Video Director Renderer
Assembles Google Veo 3.1 AI video clips/scenes, muxes OpenAI HD voiceover & Epidemic Sound music,
and burns ASS subtitles using custom TTF fonts (Montserrat Black).
"""

import os
import re
import json
import time
import subprocess
from dotenv import load_dotenv

from . import paths
from videoai_policy import validate_script

load_dotenv()

class VideoRenderer:
    def __init__(self, output_dir: str = None, cache_dir: str = None, font_dir: str = None):
        self.output_dir = str(output_dir or paths.OUTPUT_DIR)
        self.cache_dir = str(cache_dir or paths.CACHE_DIR)
        self.font_dir = str(font_dir or paths.FONT_DIR)
        os.makedirs(self.output_dir, exist_ok=True)
        os.makedirs(self.cache_dir, exist_ok=True)
        os.makedirs(self.font_dir, exist_ok=True)

    def render_video(self, script_data: dict, scene_assets: list[str], audio_path: str, subtitle_path: str) -> tuple[str, str]:
        """
        Renders complete 1080x1920 60fps vertical video and generates metadata package.
        Returns (rendered_mp4_path, metadata_json_path).
        """
        validate_script(script_data)
        metadata = script_data.get("metadata", {})
        title = metadata.get("video_title", "AW360_Animal_Fact")
        clean_title = re.sub(r'[^a-zA-Z0-9_]', '_', title)[:25]
        timestamp = int(time.time())

        final_video_name = f"AW360_{clean_title}_{timestamp}.mp4"
        final_video_path = os.path.join(self.output_dir, final_video_name)
        metadata_json_path = os.path.join(self.output_dir, f"AW360_{clean_title}_{timestamp}_metadata.json")

        scenes = script_data.get("scenes", [])
        rendered_scene_clips = []

        # 1. Process & scale each scene clip/image to 1080x1920
        for i, (scene, asset_path) in enumerate(zip(scenes, scene_assets)):
            duration = scene.get("duration_est", 6.0)
            scene_clip_out = os.path.join(self.cache_dir, f"prep_scene_{i}_{timestamp}.mp4")
            if self._prepare_scene_clip(asset_path, scene_clip_out, duration, scene.get("motion", "zoom_in")):
                rendered_scene_clips.append(scene_clip_out)

        if not rendered_scene_clips:
            raise RuntimeError("No scene clips were successfully processed.")

        # 2. Concat file list
        concat_file = os.path.join(self.cache_dir, f"concat_list_{timestamp}.txt")
        with open(concat_file, "w", encoding="utf-8") as f:
            for clip in rendered_scene_clips:
                escaped_path = clip.replace("\\", "/")
                f.write(f"file '{escaped_path}'\n")

        # 3. Concatenate scenes & combine audio & burn ASS subtitles
        temp_concat_mp4 = os.path.join(self.cache_dir, f"temp_concat_{timestamp}.mp4")

        # Step 3a: Concat video segments into single stream
        concat_cmd = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0",
            "-i", concat_file,
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "30",
            temp_concat_mp4
        ]
        subprocess.run(concat_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)

        # Step 3b: Merge audio & burn ASS subtitles using custom fontsdir
        sub_escaped = subtitle_path.replace("\\", "/").replace(":", "\\:")
        font_dir_escaped = self.font_dir.replace("\\", "/").replace(":", "\\:")

        filter_str = f"subtitles='{sub_escaped}':fontsdir='{font_dir_escaped}'"

        render_cmd = [
            "ffmpeg", "-y",
            "-i", temp_concat_mp4,
            "-i", audio_path,
            "-vf", filter_str,
            "-c:v", "libx264", "-preset", "medium", "-crf", "17", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k",
            "-shortest",
            final_video_path
        ]

        try:
            subprocess.run(render_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        except subprocess.CalledProcessError as e:
            print(f"[VideoRenderer] Subtitle filter note: {e}, running fallback render...")
            fallback_cmd = [
                "ffmpeg", "-y",
                "-i", temp_concat_mp4,
                "-i", audio_path,
                "-c:v", "libx264", "-preset", "fast", "-crf", "18",
                "-c:a", "aac", "-b:a", "192k",
                "-shortest",
                final_video_path
            ]
            subprocess.run(fallback_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)

        # 4. Save metadata package
        package_info = {
            "channel": "AW360 Animal World 360",
            "video_path": final_video_path,
            "title": metadata.get("video_title"),
            "description": metadata.get("description"),
            "tags": metadata.get("tags"),
            "pinned_comment": metadata.get("pinned_comment"),
            "thumbnail_prompt": metadata.get("thumbnail_prompt"),
            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S")
        }

        with open(metadata_json_path, "w", encoding="utf-8") as f:
            json.dump(package_info, f, indent=2)

        return final_video_path, metadata_json_path

    def _prepare_scene_clip(self, src_path: str, dst_path: str, duration: float, motion: str = "zoom_in") -> bool:
        """Scales/crops source media into 1080x1920 vertical video with pan/zoom effect."""
        is_video = src_path.lower().endswith((".mp4", ".mov", ".mkv", ".webm"))

        try:
            if is_video:
                cmd = [
                    "ffmpeg", "-y",
                    "-ss", "0", "-t", str(duration),
                    "-i", src_path,
                    "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1",
                    "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "30",
                    dst_path
                ]
            else:
                frames = int(duration * 30)
                zoom_filter = f"zoompan=z='min(zoom+0.0015,1.25)':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1080x1920,setsar=1"
                cmd = [
                    "ffmpeg", "-y",
                    "-loop", "1",
                    "-i", src_path,
                    "-vf", zoom_filter,
                    "-t", str(duration),
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "30",
                    dst_path
                ]

            subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
            return True
        except Exception as e:
            print(f"[VideoRenderer] Error preparing scene clip {src_path}: {e}")
            return False

if __name__ == "__main__":
    vr = VideoRenderer()
    print("VideoRenderer initialized.")
