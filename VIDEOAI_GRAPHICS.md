VideoAI graphics tools — mandatory Epidemic audio

**House look (2026-09-13):** the plates, chyrons, sidebar cards, exhibits and thumbnails for every production come from `videoai_graphics/broadcast.py` (House graphics section of PRODUCTION_RULES.md); the overlay presets below remain for animated lower thirds, tickers and the Epidemic soundtrack.

This post-production layer adds animated graphic overlays, styled captions, and an Epidemic soundtrack to an edited video. It uses Python's standard library and FFmpeg/libass, with no additional Python packages required.

Prerequisites: Python 3.11 or newer (tested with 3.11), FFmpeg and ffprobe on PATH or supplied through `--ffmpeg`/`--ffprobe`, and an Epidemic account MCP API key with music/SFX download access. The FFmpeg build needs libass, libx264, AAC encoding, and the standard audio mixing filters including `sidechaincompress` and `alimiter`. NVIDIA NVENC is optional; CPU rendering uses libx264. The tool reads its configuration relative to the repository and has no dependency on a particular drive letter.

Every video render requires fresh music and sound effects from Epidemic's official API. This applies to `render`, `demo --render`, and the Python `render_video` and `render_synthetic` functions. There is no silent mode, offline audio fallback, alternate provider, or option to disable either music or SFX. Missing credentials, API errors, empty searches, unusable downloads, or invalid cues stop the render before the final video is published. `compile` and `demo` without `--render` only write text/JSON sidecars and remain offline.

Continue using OpenAI for narration. Supply an edited source with its narration, dialogue, or game audio; this tool adds the Epidemic score and effects. Music is lowered under source audio, and each original audio stream is mixed separately into a corresponding output stream. A silent source receives one soundtrack stream. Audio is encoded as stereo AAC, so it is no longer copied byte for byte. Use an input without an existing music bed or already-added effects to avoid layering duplicate soundtracks. The tool cannot separate music that has already been baked into source audio.

Authentication uses `EPIDEMIC_SOUND_API_KEY` from the process environment, or `.env` in the repository root when the environment variable is absent. The key is sent only to the official MCP endpoint; asset downloads do not receive it. This is the account API documented in [Epidemic's MCP guide](https://developers.epidemicsound.com/docs/mcp/). No credentials belong in a cue sheet, command argument, or rendered metadata.

| Tool | What it adds |
| --- | --- |
| Four presets | Political red, space cyan, gaming lime, and reaction violet; consistent type, accent lines, and dark panels. |
| Animated lower thirds | Label, headline, optional subtitle, accent strip, and slide/fade entrance. |
| Title cards and callouts | Wrapped headlines, supporting copy, and contextual labels with timed entrances. |
| Badges and tickers | Short section labels and scrolling text in a clipped ticker lane. |
| Progress bars | Animated progress across a timed segment. |
| Reaction frame | Decorative inset border and label. The source must already contain the inset video; this graphic does not insert a reaction clip. |
| Captions | Clean phrase, active-word highlight, or karaoke styles; word timing, phrase/gap grouping, two-line wrapping, configurable position and colors. |
| Subtitle export | ASS for the styled render and SRT for editable plain captions. |
| Required soundtrack | Live Epidemic instrumental music and timed sound effects, with category defaults, fades, source-aware music ducking, and limiting. |

The caption and graphics defaults use separate regions. Position presets are starting points rather than subject detection. The tool does not automatically resolve collisions between multiple simultaneous graphic cues or custom caption positions. Schedule graphics in each lane sequentially, then preview long text and check that faces, action, source labels, and player controls remain readable. When supplying new captions, use a source export without already-burned duplicate captions.

Run from the repository root (locally, `A:\AI\VideoAI`). These PowerShell examples use the project's virtual environment; replace `& .\.venv\Scripts\python.exe` with your Python 3.11+ interpreter, such as `python`, when using another environment:

```powershell
# Inspect the commands without starting any generation.
& .\.venv\Scripts\python.exe .\graphics_tool.py --help

# Create an editable example cue sheet plus ASS and SRT files.
& .\.venv\Scripts\python.exe .\graphics_tool.py demo --preset space --output-dir .\output\graphics_space

# Render a vertical graphics preview with live Epidemic music and SFX.
& .\.venv\Scripts\python.exe .\graphics_tool.py demo --preset gaming --output-dir .\output\graphics_gaming_vertical --width 720 --height 1280 --render --encoder auto

# Compile your cue sheet without rendering video.
& .\.venv\Scripts\python.exe .\graphics_tool.py compile --config .\my_graphics.json --output .\output\my_graphics.ass --srt .\output\my_graphics.srt

# Add graphics and mandatory Epidemic audio to a source containing narration/dialogue.
& .\.venv\Scripts\python.exe .\graphics_tool.py render --config .\my_graphics.json --input .\output\clean_video.mp4 --output .\output\finished_video.mp4 --encoder auto --fonts-dir .\assets\fonts
```

Run a command with `--help` for its exact options. `--encoder auto` attempts NVIDIA encoding and reports any CPU fallback. `--encoder cpu` uses libx264. Existing output files are protected unless `--overwrite` is supplied. The input video itself cannot be overwritten. This version exports SDR H.264: PQ/HLG HDR footage must be converted to SDR first. Rotated or non-square-pixel input also needs normalization before processing.

CPU encoding fallback reuses the same required Epidemic assets; it never falls back to different audio. Downloads are fresh for each render and live only in that job's temporary directory. Successful results include an `audio_manifest`, also embedded in the video's comment metadata, identifying the music and effects used without including secret or signed URLs.

Editable starter cue sheets are in `graphics_examples`: `political.json`, `space.json`, `gaming.json`, `reaction.json`, and `gaming_portrait.json`. Copy one to a production-specific file, replace all demonstration text and word timings, and align the graphic cues to the actual edit. The supplied timings are illustrative and do not represent generated narration.

A cue sheet combines graphics and words. Times are seconds. `width` and `height` define a compilation/demo canvas; rendering uses the actual source video's dimensions. A portrait example:

```json
{
  "preset": "space",
  "width": 1080,
  "height": 1920,
  "duration": 8,
  "font_name": "Arial",
  "audio": {
    "provider": "epidemic",
    "music": {"query": "cinematic ambient space", "gain_db": -24},
    "sfx": [
      {"query": "short sci fi transition", "start": 3.2, "duration": 1, "gain_db": -14}
    ]
  },
  "captions": {
    "style": "highlight",
    "position": "bottom",
    "words_per_caption": 4
  },
  "words": [
    {"word": "A", "start": 0.5, "end": 0.7},
    {"word": "closer", "start": 0.7, "end": 1.1},
    {"word": "look", "start": 1.1, "end": 1.4},
    {"word": "at", "start": 1.4, "end": 1.6},
    {"word": "the", "start": 1.6, "end": 1.8},
    {"word": "mission.", "start": 1.8, "end": 2.3}
  ],
  "overlays": [
    {"type": "lower_third", "start": 0, "end": 3, "label": "MISSION BRIEF", "title": "Beyond the atmosphere", "subtitle": "Space / Chapter 01"},
    {"type": "title_card", "start": 3.2, "end": 5.2, "label": "NEXT", "title": "The next frontier", "subtitle": "A new perspective"},
    {"type": "callout", "start": 5.5, "end": 8, "label": "CONTEXT", "title": "Look closer", "subtitle": "Add a concise detail here."},
    {"type": "progress_bar", "start": 0, "end": 8}
  ]
}
```

Each overlay requires `type`, `start`, and `end`. Text uses `title`, optional `subtitle`, and optional `label`. A ticker may use `text` instead of `title`. Optional `x`, `y`, and `width` are fractions of the canvas, and `color` is a six-digit RGB value such as `#38BDF8`. The compiler rejects text that cannot fit its region rather than silently cutting it off. Keep lower-third titles and subtitles concise.

Omitting `audio` still requires Epidemic: the selected visual preset supplies a music query and a short effect cue. Political uses documentary instrumentals, space uses ambient cinematic music, gaming uses energetic electronic music, and reaction uses playful instrumentals. Customize `audio.music.query` and each `audio.sfx` cue for the actual scene. Default gains are -24 dB for music and -14 dB for effects; allowed ranges are -36 to -6 dB and -30 to 0 dB respectively. A supplied SFX list must contain at least one cue lasting at least 0.02 seconds inside the video, including after trimming to the downloaded asset. Local file substitutions and disabled/empty music or SFX settings are rejected. Times are relative to the finished video, not the source recording before cuts.

Caption options include `style` (`clean`, `highlight`, `karaoke`), `font_name`, `font_size`, `words_per_caption`, `max_chars`, `position` (`bottom`, `center`, `top`), normalized `y`, `uppercase`, `color`, `active_color`, and `outline_color`. Font sizes are in canvas pixels when explicitly provided. Use an installed font family name, or provide a directory containing matching font files. No fonts are downloaded automatically.

The existing narration functions already return `word_timestamps` in the required `word/start/end` shape. Save those timestamps in `words` after synthesizing the final OpenAI narration; do not estimate them again after changing the voiceover. These tools style supplied timestamps and do not transcribe or improve inaccurate alignment.

For political videos, use clean captions and brief contextual labels. For space videos, use mission labels and technical callouts. For gaming, use highlighted phrases and cue action labels to verified moments. For reaction videos, leave source dialogue and the commentator's face unobstructed and use the inset frame only around an already-composited reaction window.

Graphics rendering stages the new picture and mixed soundtrack, checks the result with ffprobe, and only then publishes the requested output path. The mandatory provider rule belongs to this graphics tool's render entrypoints. Older standalone VideoAI recipe scripts retain their separate render implementations; route their completed edits through this finishing tool to enforce the same final-export rule. The earlier Python-environment issues in those original generation pipelines remain separate.

The original graphics-only release was visually checked in both orientations. Its old silent previews and byte-identical audio-copy check describe that earlier release; current renders require the Epidemic mix. On September 11, 2026, two live official-API renders passed: an eight-second vertical NVIDIA render and a three-second CPU render with two source audio tracks. Both exported music/SFX provenance; measured test tones confirmed the two original tracks remained separate. Regression checks cover required provider execution, rejected bypasses, failure before publication, and the graphics/compiler behavior. Run them from the project root:

```powershell
& .\.venv\Scripts\python.exe -B -m unittest discover -s .\graphics_tests -p 'test_graphics_*.py'
```
