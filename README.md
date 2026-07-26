# VideoAI

A Python toolkit for automated short-form video production. It selects source
footage, scores it with licensed music, strips unwanted subjects out of the
frame, and renders finished vertical cuts with FFmpeg.

## What it does

- **Automated editing** — picks a segment from a source clip, crops to 9:16,
  applies colour grading and fades, and renders a finished short.
- **Music scoring** — searches the Epidemic Sound catalogue for a track matching
  a mood query, caches the download, and mixes it under the footage.
- **Subject detection** — OpenCV-backed passes that scan frames for people or
  body parts so clips can be filtered down to hardware-only footage.
- **Voiceover** — narration through a local Voicebox TTS server, Edge TTS, or
  OpenAI voices.
- **Licence checking** — `check_licensing.py` verifies the state of your
  Epidemic Sound account before you publish.

## Requirements

- Python 3.12+
- [FFmpeg](https://ffmpeg.org/) and `ffprobe` on your `PATH`
- API keys for the services you intend to use (see below)

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows;  source .venv/bin/activate elsewhere
pip install -r requirements.txt   # or: uv sync
cp .env.example .env              # then fill in keys and media paths
```

All file locations are configured through `.env`. Nothing is hardcoded — set
`MEDIA_ROOT` to wherever your source footage lives and the per-category folders
are derived from it, or override each one individually.

## Usage

```bash
python main.py                    # main pipeline
python create_military_short.py   # military-footage short builder
python check_licensing.py         # verify Epidemic Sound licensing
python search_music.py            # search the music catalogue
```

## Licensing note

Music retrieved through the Epidemic Sound API is licensed to **your** account.
Downloaded audio lives in `assets/` and is deliberately excluded from this
repository — do not redistribute it. Likewise, `output/` holds rendered video
and is not tracked.

Source footage is your own responsibility: confirm the rights on anything you
publish, particularly third-party or government-released material.
