"""
AW360 Animal World 360 - Budget-Conscious Video Director Pipeline
Supports --mode stock (Free $0.00 video media), --mode hybrid, or --mode veo.
Protects your Google API monthly spend cap ($10.00 limit).
"""

import os
import sys
import json
import time

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

from dotenv import load_dotenv

# Make the project root importable so the root-level modules resolve from a clone.
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aw360.trend_researcher import TrendResearcher
from aw360.scriptwriter import DirectorScriptwriter
from aw360.voiceover_generator import VoiceoverGenerator
from aw360.audio_director import AudioDirector
from aw360.media_sourcer import MediaSourcer
from aw360.subtitle_burner import SubtitleBurner
from aw360.video_renderer import VideoRenderer

load_dotenv()

class AW360VideoDirector:
    def __init__(self, mode: str = "stock"):
        self.mode = mode.lower()
        print("===============================================================")
        print(f"   [AW360] ANIMAL WORLD 360 - AI VIDEO DIRECTOR ({self.mode.upper()} MODE)  ")
        print("===============================================================")
        self.researcher = TrendResearcher()
        self.scriptwriter = DirectorScriptwriter()
        self.voiceover_gen = VoiceoverGenerator()
        self.audio_director = AudioDirector()
        self.media_sourcer = MediaSourcer(mode=self.mode)
        self.subtitle_burner = SubtitleBurner()
        self.renderer = VideoRenderer()

    def create_video(self, custom_topic: str = None) -> dict:
        start_time = time.time()

        # Print Cost Estimate
        if self.mode == "stock":
            print("💰 Estimated Cost: ~$0.0005 per video (Gemini 2.5 Flash script only!). Media cost: $0.00")
        elif self.mode == "hybrid":
            print("💰 Estimated Cost: ~$0.001 - $0.15 (Stock video first, fallback to Veo if needed).")
        else:
            print("⚠️ MODE VEO: Generates full Veo 3.1 AI videos (~$0.15 - $0.50 per video run).")

        # Step 1: Research Trending Topic
        print("\n[1/6] Researching 1M-View Viral Animal Topic...")
        topic_info = self.researcher.discover_trending_topic(custom_topic)
        print(f"   > Topic: {topic_info.get('topic_name')}")
        print(f"   > Title: {topic_info.get('viral_title')}")
        print(f"   > Hook: {topic_info.get('hook')}")

        # Step 2: Write Director Script with Gemini 2.5 Flash
        print("\n[2/6] Writing Script & Storyboard with Gemini 2.5 Flash...")
        script_data = self.scriptwriter.generate_script(topic_info)
        scenes = script_data.get("scenes", [])
        metadata = script_data.get("metadata", {})
        print(f"   > Total Scenes: {len(scenes)}")

        # Step 3: Generate Voiceover & Word Timestamps
        print("\n[3/6] Generating Voiceover & Word Timestamps...")
        full_text = script_data.get("full_voiceover_text", "")
        voiceover_file, word_timestamps, total_duration = self.voiceover_gen.generate_narration(full_text)
        print(f"   > Narration Duration: {total_duration:.1f} seconds")
        print(f"   > Word Timestamps: {len(word_timestamps)} words processed")

        # Step 4: Background Music & Audio Mixing
        print("\n[4/6] Selecting Epidemic Sound Music & Mixing Audio...")
        music_mood = metadata.get("music_mood", "epic")
        bg_music_track = self.audio_director.fetch_background_music(music_mood)
        mixed_audio_file = os.path.join(self.renderer.cache_dir, f"mixed_audio_{int(start_time)}.aac")
        self.audio_director.mix_narration_and_music(voiceover_file, bg_music_track, mixed_audio_file, total_duration)

        # Step 5: Source HD Visual Assets & Generate ASS Subtitles
        print(f"\n[5/6] Sourcing Visual Assets (Mode: {self.mode.upper()}) & ASS Subtitles...")
        scene_assets = []
        for scene in scenes:
            asset = self.media_sourcer.fetch_scene_media(scene)
            scene_assets.append(asset)
            print(f"   > Scene {scene.get('scene_id')}: {asset}")

        sub_file = self.subtitle_burner.generate_ass_subtitles(word_timestamps)

        # Step 6: Render Final Video & Package Metadata
        print("\n[6/6] Rendering Finished 1080x1920 Vertical Video with FFmpeg...")
        final_mp4, metadata_file = self.renderer.render_video(script_data, scene_assets, mixed_audio_file, sub_file)

        elapsed = time.time() - start_time
        print("\n===============================================================")
        print(f"SUCCESS: VIDEO CREATION COMPLETE IN {elapsed:.1f} SECONDS!")
        print(f"Video Path:    {final_mp4}")
        print(f"Metadata Path: {metadata_file}")
        print("===============================================================\n")

        with open(metadata_file, "r", encoding="utf-8") as f:
            package_summary = json.load(f)

        return package_summary

if __name__ == "__main__":
    mode = "stock"
    topic_query = None

    for arg in sys.argv[1:]:
        if arg.startswith("--mode="):
            mode = arg.split("=")[1].lower()
        elif arg in ["stock", "hybrid", "veo"]:
            mode = arg.lower()
        else:
            topic_query = arg

    director = AW360VideoDirector(mode=mode)
    result = director.create_video(topic_query)
    print("\n--- READY FOR USER REVIEW & UPLOAD ---")
    print(f"Title: {result.get('title')}")
    print(f"Description:\n{result.get('description')}")
    print(f"Pinned Comment: {result.get('pinned_comment')}")
