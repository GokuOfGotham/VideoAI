"""
AW360 Animal World 360 - High Impact Subtitle & Caption Generator
Generates ASS subtitles with custom viral typography (Montserrat Black / Anton),
dynamic yellow/cyan active word highlights, and heavy black stroke outlines.
"""

import os

from . import paths

class SubtitleBurner:
    def __init__(self, font_dir: str = None, cache_dir: str = None):
        self.font_dir = str(font_dir or paths.FONT_DIR)
        self.cache_dir = str(cache_dir or paths.CACHE_DIR)
        os.makedirs(self.font_dir, exist_ok=True)
        os.makedirs(self.cache_dir, exist_ok=True)

    def generate_ass_subtitles(self, word_timestamps: list, output_path: str = None, font_name: str = "Montserrat-Black") -> str:
        """
        Creates an Advanced SubStation Alpha (.ass) subtitle file using premium TTF fonts
        and word-by-word active highlight animation.
        """
        if not output_path:
            output_path = os.path.join(self.cache_dir, "viral_subtitles.ass")

        header = f"""[Script Info]
Title: AW360 Dynamic High Impact Subtitles
ScriptType: v4.00+
WrapStyle: 0
ScaledBorderAndShadow: yes
YCbCr Matrix: None
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: ViralStyle,{font_name},68,&H00FFFFFF,&H0000FFFF,&H00000000,&H90000000,-1,0,0,0,105,105,1,0,1,5,3,2,50,50,850,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

        events = []
        if not word_timestamps:
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(header)
            return output_path

        # Group words into 2-word punchy phrases
        chunk_size = 2
        chunks = [word_timestamps[i:i + chunk_size] for i in range(0, len(word_timestamps), chunk_size)]

        for chunk in chunks:
            if not chunk:
                continue
            start_sec = chunk[0]["start"]
            end_sec = chunk[-1]["end"]

            if end_sec <= start_sec:
                end_sec = start_sec + 0.5

            start_ass = self._format_ass_time(start_sec)
            end_ass = self._format_ass_time(end_sec)

            # Generate word highlights
            phrase_parts = []
            for w in chunk:
                clean_w = w["word"].upper().strip()
                # Apply bright yellow highlight (\c&H0000FFFF&) with subtle font scaling
                phrase_parts.append(f"{{\\c&H0000FFFF&}}{clean_w}{{\\c&H00FFFFFF&}}")

            text_line = " ".join(phrase_parts)
            line_str = f"Dialogue: 0,{start_ass},{end_ass},ViralStyle,,0,0,0,,{text_line}"
            events.append(line_str)

        full_content = header + "\n".join(events) + "\n"

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(full_content)

        return output_path

    def _format_ass_time(self, seconds: float) -> str:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        centisecs = int((seconds - int(seconds)) * 100)
        return f"{hours}:{minutes:02d}:{secs:02d}.{centisecs:02d}"

if __name__ == "__main__":
    sb = SubtitleBurner()
    path = sb.generate_ass_subtitles([{"word": "Did", "start": 0.0, "end": 0.4}, {"word": "you", "start": 0.4, "end": 0.8}])
    print("Generated ASS Subtitles Path:", path)
