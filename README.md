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
- **Space media** — `space_media_sourcer.py` sources spaceflight footage and
  imagery from NASA and SpaceX for space videos, ahead of the generic stock
  libraries.
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

### Space media (NASA / SpaceX)

Space scenes are sourced from NASA and SpaceX *before* the generic stock
libraries — the footage is public domain and a far better match than whatever
"rocket" returns from a stock search. The tier only engages when the scene
keywords look like spaceflight or astronomy, so it costs nothing on the gaming
and military scenes.

```bash
python space_media_sourcer.py --query "saturn v apollo launch" --duration 6
python space_media_sourcer.py --query "deep space nebula" --stills-only
python space_media_sourcer.py --check          # which upstream APIs are reachable
python space_media_sourcer.py --attribution    # print the credit ledger
```

Sources, tried in order:

1. **NASA Image and Video Library** — real MP4 footage, no API key needed.
2. **SpaceX** — launch photography from each launch's Flickr originals, plus
   launch webcasts, whose YouTube ids are handed to the b-roll pipeline so the
   footage gets cut the same way.
3. **NASA library again, broadened** — NASA's search is literal, so
   `rocket grid fins deployment steering` matches nothing while `rocket`
   matches thousands of clips. A miss retries with progressively shorter
   queries anchored on the space terms before anything else is tried.
4. **NASA APOD** — high-resolution astronomy stills. Uses `NASA_API_KEY`;
   without one it falls back to the heavily rate-limited `DEMO_KEY`. APOD has
   no search endpoint — it only serves a date or a random pick — so it is
   consulted **only for astronomy scenes** (nebula, eclipse, night sky). A
   scene about landing legs never gets a random galaxy.

Stills get a slow Ken Burns push rather than being held static, because a
frozen frame under narration reads as a broken video.

> **SpaceX API availability.** The public instance at `api.spacexdata.com` goes
> down for stretches at a time — it was returning Cloudflare `525` throughout
> this feature's development. Launch data is cached to disk on first success so
> the tier keeps working through an outage, and every call treats absence as
> normal and falls through to NASA. Point `SPACEX_API_BASE` at a mirror if you
> run one.

## Licensing note

Music retrieved through the Epidemic Sound API is licensed to **your** account.
Downloaded audio lives in `assets/` and is deliberately excluded from this
repository — do not redistribute it. Likewise, `output/` holds rendered video
and is not tracked.

Source footage is your own responsibility: confirm the rights on anything you
publish, particularly third-party or government-released material.

NASA material is public domain, with the caveats NASA itself publishes: its
logos and insignia are restricted, and the media library hosts some third-party
content that only NASA has cleared. SpaceX has released its launch photography
into the public domain. APOD is the exception — it frequently features privately
owned astrophotography, so entries carrying a `copyright` field are recorded as
**permission required** rather than public domain. All of it lands in
`assets/materials/space/ATTRIBUTION.md`.

YouTube b-roll defaults to `YOUTUBE_BROLL_LICENSE=cc`, keeping only videos
YouTube reports as Creative Commons. Those permit reuse **with credit** — the
generated `assets/materials/youtube/ATTRIBUTION.md` lists title, channel, source
URL and licence for every cached clip, and that credit has to travel with the
finished video. Setting the variable to `any` widens the pool to standard-licence
uploads, which are not cleared for reuse; clearing them is on you.
