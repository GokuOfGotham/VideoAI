# VideoAI

A Python toolkit for automated short-form video production. It selects source
footage, scores it with licensed music, strips unwanted subjects out of the
frame, and renders finished vertical cuts with FFmpeg.

## What it does

- **Automated editing** — picks a segment from a source clip, crops to 9:16,
  applies colour grading and fades, and renders a finished short.
- **Music scoring** — searches the Epidemic Sound catalogue for a track matching
  a mood query, caches the download, and mixes it under the footage.
- **YouTube b-roll** — `youtube_broll.py` fills gaps the stock libraries can't,
  pulling only the seconds it needs, cutting on the longest uninterrupted shot,
  and logging credit for everything it caches.
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
pip install -e .                  # or: uv sync
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

### YouTube b-roll

Both video agents — `pipeline.py` and the AW360 director — fall through to
YouTube when Pexels and Pixabay return nothing usable. The tier is also a
standalone tool:

```bash
python youtube_broll.py --query "aerial drone forest fog" --duration 6
python youtube_broll.py --query "storm clouds timelapse" --count 3
python youtube_broll.py --attribution      # print the credit ledger
```

What it does per clip:

1. Searches YouTube behind its Creative Commons filter, then re-checks the
   licence each candidate actually reports.
2. Rejects live streams, age-gated uploads, anything under
   `YOUTUBE_BROLL_MIN_HEIGHT`, and sources too short to cut from.
3. Downloads a probe window instead of the whole video — intro and outro
   trimmed, offset derived from the query so repeated scenes don't reuse the
   same footage.
4. Runs FFmpeg scene detection over that window and cuts from the longest
   uninterrupted shot, so the clip doesn't straddle an edit.
5. Normalises to a muted 1080x1920 clip. B-roll is video-only; narration and
   music are added by the renderer, so source audio is never downloaded.

Everything is cached under `assets/materials/youtube/`. A repeat request for the
same query and clip length reuses the clip it already cut — without that, YouTube
reorders its results between runs and the same scene would download something
new each time. `--count` still returns distinct clips.

Tuning lives in `.env` (`YOUTUBE_BROLL_*`) — most usefully
`YOUTUBE_BROLL_PRIORITY` to move the tier ahead of the stock APIs (`first`) or
switch it off (`off`).

## Licensing note

Music retrieved through the Epidemic Sound API is licensed to **your** account.
Downloaded audio lives in `assets/` and is deliberately excluded from this
repository — do not redistribute it. Likewise, `output/` holds rendered video
and is not tracked.

Source footage is your own responsibility: confirm the rights on anything you
publish, particularly third-party or government-released material.

YouTube b-roll defaults to `YOUTUBE_BROLL_LICENSE=cc`, keeping only videos
YouTube reports as Creative Commons. Those permit reuse **with credit** — the
generated `assets/materials/youtube/ATTRIBUTION.md` lists title, channel, source
URL and licence for every cached clip, and that credit has to travel with the
finished video. Setting the variable to `any` widens the pool to standard-licence
uploads, which are not cleared for reuse; clearing them is on you.
