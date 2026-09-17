# VideoAI editing room

Epidemic (music, effects, voices via MCP) and the broadcast graphics covered the
music supervisor and the graphics desk. `videoai_editroom/` adds the other
departments of a post-production room as plain Python over FFmpeg, OpenCV,
numpy and faster-whisper, and `editroom_tool.py` exposes each one as a command
that prints a single JSON report. Nothing here bypasses the production policy:
a timeline renders through `edit_tools`/`graphics_tool.py`, and
`policy_tool.py check` is still the gate before delivery.

```powershell
& .\.venv\Scripts\python.exe .\editroom_tool.py --help
& .\.venv\Scripts\python.exe -B -m unittest discover -s .\editroom_tests
```

| Department | Tool | Command | What it does |
|---|---|---|---|
| Assistant editor | `TranscribeMedia` | `transcribe` | Word-timed transcript with sentence segments, timecodes and speaker turns. Local faster-whisper (GPU when its runtime is present, else CPU) or `--engine openai`. Speaker labels are pause/pitch heuristics unless a diarizer is supplied; the report says so. |
| | `SyncMulticam` | `sync` | Envelope cross-correlation of every angle/audio file against a reference; offset in seconds, frames and timecode with a confidence. Positive offset = the angle runs behind the reference, trim it from its head. |
| | `DetectSilence` | `silence` | FFmpeg `silencedetect` dead air plus, with a transcript, filler words and flubbed retakes. Candidates only; `keep_ranges()` turns them into the surviving ranges. |
| | `GenerateProxies` | `proxies` | H.264 proxies at a chosen height (HDR sources tone-mapped), skipping ones already made. Conform back to the native sources for export. |
| Picture editor | `GetTimelineState` | `timeline FILE` | The sequence as JSON: clips with in/out, start/end, timecodes, gaps, markers, sources. |
| | `ApplyEditAction` | `timeline FILE --action '{...}'` | `insert`, `overwrite`, `append`, `ripple_delete`, `lift`, `trim`, `split`, `move`, `reorder`, `set`, `add_marker`, `remove_marker`. Clips never overlap; length changes ripple. |
| | `BuildAssembly` | `assemble` | Rough cut from a transcript scored by `--brief`/`--keyword`, explicit `--highlight in-out` ranges, optionally limited by a silence report; segments get 0.1 s lead / 0.3 s tail. |
| | `ExportXML` | `export` | FCPXML 1.9 (Resolve/Premiere) or CMX3600 EDL. |
| | render | `render` | V1 through `edit_tools` (same segment renderer as the recipes). Clean edit only; finish with `graphics_tool.py render`. |
| VFX & graphics | `SearchVisualBroll` | `broll` | A local media bin, the Creative-Commons YouTube sourcer and the NASA sourcer, in order, from a query or a transcript passage; provenance and attribution in the result. |
| | `GenerateCaptions` | `captions` | SRT plus a house-styled ASS (`videoai_graphics.broadcast` header and tag); cues break on speaker change, sentence end, pause and width. |
| | `AutoReframe` | `reframe` | YOLO person tracking (falls back to motion saliency), dead zone + smoothing, native-height crop to 9:16 or any narrower aspect; audio copied. |
| Audio mixer | `CleanDialogue` | `clean` | High-pass, spectral denoise, de-ess, gentle compression, loudness to a target. No stretching or pitch shifting. |
| | `ApplyAudioDucking` | `duck` | Gain keyframes from the dialogue envelope (attack/hold/release), applied as a `volume` expression; mixed or as a music stem. Keyframes can be written out for the NLE. |
| | `GenerateADR` | `adr` | Re-records a ruined range with the approved Cedar preset, fills with room tone and crossfades in. Reports `rewrite_needed` when the take is longer than the hole instead of squeezing it. The house voice is not a clone of the original speaker. |
| Colorist | `MatchColor` | `match` | LAB statistics transfer from a reference shot, written as a `.cube` LUT and applied with `lut3d`; reports the distance before/after. |
| | `ApplyLUT` | `lut` | Any `.cube`, or a built-in: `rec709`, `hlg_to_rec709`, `pq_to_rec709` (colour-managed zscale/tonemap), `slog3_to_rec709`, `clog3_to_rec709`, `vlog_to_rec709`, `teal_orange`, `filmic_contrast`, `news_neutral`. `looks` lists them. |

## A script-based edit end to end

```powershell
$py = ".\.venv\Scripts\python.exe"
& $py .\editroom_tool.py transcribe .\raw\interview.mp4 --output .\work\transcript.json
& $py .\editroom_tool.py silence .\raw\interview.mp4 --transcript .\work\transcript.json --output .\work\silence.json
& $py .\editroom_tool.py assemble .\raw\interview.mp4 --transcript .\work\transcript.json `
    --brief "why the launch was scrubbed" --silence-report .\work\silence.json --target-seconds 55 --output .\work\cut.json
& $py .\editroom_tool.py timeline .\work\cut.json                                   # inspect
& $py .\editroom_tool.py timeline .\work\cut.json --action '{"action":"split","clip_id":"c2","at":12.4}'
& $py .\editroom_tool.py render .\work\cut.json --output .\work\clean.mp4 --work .\work\segments
& $py .\editroom_tool.py captions .\work\transcript.json --output-base .\work\captions --kind main
& $py .\editroom_tool.py export .\work\cut.json --output .\work\cut.fcpxml      # or --format edl
```

Then the usual finishing pass: `graphics_tool.py render` for the broadcast
plates, captions and the required Epidemic score, and `policy_tool.py check`
on the production plan. The transcript's word timings describe the source; the
final captions must be re-timed from the finished narration/audio
(PRODUCTION_RULES.md).

## Timeline format

```json
{"name": "cut", "fps": 30, "width": 1920, "height": 1080,
 "tracks": [{"id": "V1", "kind": "video", "clips": [
    {"id": "c1", "name": "hook", "src": "raw/interview.mp4", "src_in": 12.0, "src_out": 15.5,
     "start": 0.0, "speed": 1.0, "audio": "source"}]},
   {"id": "A1", "kind": "audio", "clips": []}],
 "markers": [{"time": 0.0, "name": "HOOK"}],
 "production_review": {}}
```

Clip options pass straight to `edit_tools.render_segment`: `speed`, `audio`
(`source`, `bed`, `mute`), `fx: "hit"`, `cx` for a 9:16 crop centre, `text`,
`hold`. A clip with `hold` freezes its last frame for that long.

## What the tools do not claim

- Speaker labels from the heuristic are turns, not identities. Name people
  from the footage before they go on a chyron.
- Silence, filler and retake ranges are candidates. The policy keeps pauses
  that carry tension or setup.
- `sync` confidence is a correlation ratio; confirm a low-confidence angle
  on a clap or a transient.
- `match` equalises colour statistics; continuity is judged on adjacent
  frames by eye. The log transforms handle tonality, not the camera gamut.
- `reframe` never upscales: a 1920x1080 source becomes 608x1080.
- `adr` uses the approved narration voice. It is labelled as re-voiced; it
  is not the original speaker.

Tests (`editroom_tests/`) run on FFmpeg-generated media with mocked
providers, so they cost nothing and need no API keys.
