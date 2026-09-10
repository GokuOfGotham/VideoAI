"""Subtitle Engine for VideoAI.

Generates ASS (Advanced SubStation Alpha) subtitle files with TikTok/Shorts style
active-word highlighting, large prominent typography, and centered focal positioning.
"""

from pathlib import Path
from typing import Dict, List, Optional


def create_ass_subtitles(
    word_timestamps: List[Dict],
    output_path: str,
    font_name: str = "Impact",
    font_size: int = 68,  # Large legible text for 1080x1920 vertical canvas
    words_per_caption: int = 2,  # 2 words per chunk for fast, high-retention TikTok cadence
    active_color_hex: str = "00FFFF",  # Bright Yellow in BGR ASS format (&H0000FFFF&)
    base_color_hex: str = "FFFFFF",   # Pure White
    alignment: int = 5,  # 5 = Middle Center (focal zone), 2 = Bottom Center
    vertical_margin: int = 0
) -> str:
    """Creates a stylized ASS subtitle file with large, centered TikTok/Shorts captions."""
    ass_header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font_name},{font_size},&H00{base_color_hex}&,&H00000000&,&H00000000&,&H80000000&,-1,0,0,0,100,100,0,0,1,5,2,{alignment},50,50,{vertical_margin},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    events = []

    # Group words into small subtitle chunks (1-2 words for TikTok retention)
    chunks = _group_words(word_timestamps, max_words=words_per_caption)

    for chunk in chunks:
        chunk_start = chunk[0]["start"]
        chunk_end = chunk[-1]["end"]

        for i, current_word in enumerate(chunk):
            w_start_str = _format_ass_time(current_word["start"])
            w_end_val = chunk[i + 1]["start"] if i + 1 < len(chunk) else chunk_end
            w_end_str = _format_ass_time(w_end_val)

            text_parts = []
            for j, w in enumerate(chunk):
                word_clean = w["word"].upper()
                if j == i:
                    # High contrast yellow highlight with bold text
                    text_parts.append(f"{{\\c&H00{active_color_hex}&\\b1}}{word_clean}{{\\c&H00{base_color_hex}&\\b0}}")
                else:
                    text_parts.append(word_clean)

            line_text = " ".join(text_parts)
            event_line = f"Dialogue: 0,{w_start_str},{w_end_str},Default,,0,0,0,,{line_text}"
            events.append(event_line)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(ass_header + "\n".join(events) + "\n")

    return output_path


def _group_words(word_timestamps: List[Dict], max_words: int = 2) -> List[List[Dict]]:
    """Groups individual word timestamps into short phrase chunks."""
    chunks = []
    current_chunk = []

    for item in word_timestamps:
        current_chunk.append(item)
        if len(current_chunk) >= max_words or item["word"].endswith((".", "!", "?", ";")):
            chunks.append(current_chunk)
            current_chunk = []

    if current_chunk:
        chunks.append(current_chunk)

    return chunks


def _format_ass_time(seconds: float) -> str:
    """Formats floating seconds to ASS timestamp (H:MM:SS.cs)."""
    hrs = int(seconds // 3600)
    mins = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    centisecs = int(round((seconds - int(seconds)) * 100))
    if centisecs >= 100:
        secs += 1
        centisecs = 0
    return f"{hrs}:{mins:02d}:{secs:02d}.{centisecs:02d}"


if __name__ == "__main__":
    sample_words = [
        {"word": "Execute", "start": 0.0, "end": 0.4},
        {"word": "with", "start": 0.4, "end": 0.6},
        {"word": "relentless", "start": 0.6, "end": 1.1},
        {"word": "focus", "start": 1.1, "end": 1.5},
    ]
    out = create_ass_subtitles(sample_words, "test_subs.ass")
    print(f"Created ASS subtitles at {out}")
