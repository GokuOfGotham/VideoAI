"""VFX and graphics department: B-roll search, captions, and auto-reframe.

Captions always come out in the house broadcast system (``videoai_graphics.
broadcast``); this module only groups timed words into cues and writes the
SRT/ASS. B-roll search wraps the existing YouTube (Creative Commons) sourcer
and the NASA/space sourcer so provenance lands in the same attribution ledgers.
Auto-reframe tracks the subject with YOLO when the weights are present and
falls back to motion saliency, smooths the crop path, and re-encodes through
FFmpeg with the source audio untouched.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterable

import numpy as np

from .common import EditRoomError, audio_streams, ffprobe_json, frame_rate, run_ffmpeg, video_stream, write_json

PROJECT_ROOT = Path(__file__).resolve().parent.parent
YOLO_WEIGHTS = PROJECT_ROOT / "yolov8n.pt"


# --- SearchVisualBroll --------------------------------------------------------


def _local_bin_search(bin_dir: Path, query: str, limit: int) -> list[dict[str, Any]]:
    """Matches file names and sidecar .json/.txt notes in a media bin."""
    terms = [t for t in re.findall(r"[a-z0-9]+", query.lower()) if len(t) > 2]
    hits = []
    for path in sorted(bin_dir.rglob("*")):
        if path.suffix.lower() not in (".mp4", ".mov", ".mkv", ".webm", ".m4v"):
            continue
        haystack = path.stem.lower().replace("_", " ").replace("-", " ")
        for sidecar in (path.with_suffix(".json"), path.with_suffix(".txt")):
            if sidecar.exists():
                haystack += " " + sidecar.read_text(encoding="utf-8", errors="replace").lower()
        score = sum(1 for t in terms if t in haystack)
        if score:
            hits.append({"provider": "bin", "path": str(path), "title": path.stem, "score": score,
                         "license": "project media", "attribution": None})
    hits.sort(key=lambda h: -h["score"])
    return hits[:limit]


def search_visual_broll(query: str, *, seconds: float = 5.0, providers: Iterable[str] = ("bin", "youtube"),
                        bin_dir: str | Path | None = None, limit: int = 5, transcript_text: str | None = None,
                        exclude_video_ids: Iterable[str] = ()) -> dict[str, Any]:
    """Contextual B-roll for a transcript passage or query, with provenance.

    ``providers`` are tried in order: ``bin`` (a local folder of project media),
    ``youtube`` (Creative Commons via youtube_broll, cached and attributed) and
    ``space`` (NASA via space_media_sourcer). A transcript passage can be passed
    instead of a query; its most specific nouns become the search terms.
    """
    if transcript_text and not query.strip():
        words = re.findall(r"[A-Za-z][A-Za-z'-]+", transcript_text)
        stop = {"the", "and", "that", "this", "with", "from", "have", "they", "were", "been", "their"}
        keywords = [w for w in words if len(w) > 3 and w.lower() not in stop]
        query = " ".join(dict.fromkeys(keywords[:6]))
    if not query.strip():
        raise EditRoomError("search_visual_broll needs a query or transcript passage.")
    results: list[dict[str, Any]] = []
    tried = []
    for provider in providers:
        tried.append(provider)
        if provider == "bin":
            folder = Path(bin_dir) if bin_dir else PROJECT_ROOT / "assets" / "broll"
            if folder.exists():
                results.extend(_local_bin_search(folder, query, limit))
        elif provider == "youtube":
            from youtube_broll import fetch_broll_clip
            clip = fetch_broll_clip(query, target_duration=seconds, exclude_video_ids=list(exclude_video_ids))
            if clip:
                results.append({"provider": "youtube", "path": clip.path, "title": clip.title,
                                "channel": clip.channel, "url": clip.webpage_url, "license": clip.license,
                                "source_range": [clip.source_start, clip.source_end],
                                "attribution": f"{clip.title} by {clip.channel} ({clip.license}) {clip.webpage_url}"
                                if clip.requires_attribution else None})
        elif provider == "space":
            from space_media_sourcer import fetch_space_clip
            clip = fetch_space_clip(query, seconds)
            if clip:
                results.append({"provider": "space", "path": clip.path, "title": getattr(clip, "title", query),
                                "url": getattr(clip, "source_url", None), "license": getattr(clip, "license", "NASA"),
                                "attribution": getattr(clip, "credit", "NASA")})
        else:
            raise EditRoomError(f"Unknown B-roll provider '{provider}' (bin, youtube, space).")
        if len(results) >= limit:
            break
    return {"query": query, "seconds": seconds, "providers_tried": tried, "results": results[:limit],
            "note": "Label illustrative footage as illustrative and record the source identity and "
                    "native resolution in the source manifest (PRODUCTION_RULES.md)."}


# --- GenerateCaptions ---------------------------------------------------------


def _srt_time(seconds: float) -> str:
    ms = int(round(max(0.0, seconds) * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _ass_time(seconds: float) -> str:
    cs = int(round(max(0.0, seconds) * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h:d}:{m:02d}:{s:02d}.{cs:02d}"


def group_cues(words: list[dict[str, Any]], *, max_chars: int = 42, max_seconds: float = 4.0,
               gap: float = 0.7) -> list[dict[str, Any]]:
    """Cues that break on speaker change, sentence end, pause, length or duration."""
    cues: list[dict[str, Any]] = []
    for word in words:
        token = str(word["word"]).strip()
        if not token:
            continue
        current = cues[-1] if cues else None
        new = (current is None
               or word.get("speaker") != current.get("speaker")
               or float(word["start"]) - current["end"] > gap
               or float(word["end"]) - current["start"] > max_seconds
               or len(current["text"]) + 1 + len(token) > max_chars
               or re.search(r"[.!?]$", current["text"]))
        if new:
            cues.append({"start": float(word["start"]), "end": float(word["end"]), "text": token,
                         "speaker": word.get("speaker"), "words": [word]})
        else:
            current["text"] += " " + token
            current["end"] = float(word["end"])
            current["words"].append(word)
    for a, b in zip(cues, cues[1:]):
        a["end"] = min(a["end"] + 0.15, b["start"] - 0.02) if b["start"] - a["end"] > 0.02 else a["end"]
    return cues


def generate_captions(words: list[dict[str, Any]], *, output_base: str | Path, kind: str = "main",
                      subject: str = "default", style: str = "Narr", speaker_labels: bool = False,
                      max_chars: int | None = None, duration: float | None = None) -> dict[str, Any]:
    """SRT plus a house-styled ASS from timed words.

    ``kind`` is ``main`` (1920x1080) or ``short`` (1080x1920); ``style`` is the
    broadcast ``Narr`` or ``Quote`` style. Speaker changes always start a new
    cue; ``speaker_labels`` also prefixes the label in the SRT for review.
    Word timing must come from the final audio (AGENTS.md).
    """
    from videoai_graphics.broadcast import Theme, ass_header, caption_tag
    if kind not in ("main", "short"):
        raise EditRoomError("kind must be main or short.")
    if style not in ("Narr", "Quote"):
        raise EditRoomError("style must be Narr or Quote.")
    if duration is not None:
        bad = [w for w in words if float(w["end"]) > duration + 0.05]
        if bad:
            raise EditRoomError(f"{len(bad)} words end after the {duration}s video; retime from the final audio.")
    cues = group_cues(words, max_chars=max_chars or (28 if kind == "short" else 42))
    base = Path(output_base)
    base.parent.mkdir(parents=True, exist_ok=True)
    srt_lines = []
    for index, cue in enumerate(cues, start=1):
        text = cue["text"]
        if speaker_labels and cue.get("speaker"):
            text = f"[{cue['speaker']}] {text}"
        srt_lines += [str(index), f"{_srt_time(cue['start'])} --> {_srt_time(cue['end'])}", text, ""]
    srt_path = base.with_suffix(".srt")
    srt_path.write_text("\n".join(srt_lines), encoding="utf-8")
    theme = Theme(subject=subject)
    tag = caption_tag(kind)
    events = []
    for cue in cues:
        text = cue["text"].replace("\\", "\\\\").replace("{", "(").replace("}", ")")
        events.append(f"Dialogue: 0,{_ass_time(cue['start'])},{_ass_time(cue['end'])},{style},"
                      f"{cue.get('speaker') or ''},0,0,0,,{tag}{text}")
    ass_path = base.with_suffix(".ass")
    ass_path.write_text(ass_header(kind, theme) + "\n".join(events) + "\n", encoding="utf-8")
    return {"srt": str(srt_path), "ass": str(ass_path), "cue_count": len(cues), "kind": kind,
            "style": style, "cues": [{k: v for k, v in c.items() if k != "words"} for c in cues],
            "note": "Burn with the plate from videoai_graphics.broadcast; check timing by transcribing "
                    "the audio under each cue start (PRODUCTION_RULES.md)."}


# --- AutoReframe --------------------------------------------------------------


def _subject_centres(path: Path, *, width: int, height: int, fps: float, sample_fps: float,
                     detector: str) -> tuple[list[tuple[float, float, float]], str]:
    """Sampled (time, cx, cy) subject centres from YOLO people/faces or motion saliency."""
    import cv2
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        raise EditRoomError(f"OpenCV could not open {path.name}.")
    step = max(1, int(round(fps / sample_fps)))
    model = None
    method = "motion"
    if detector in ("auto", "yolo") and YOLO_WEIGHTS.exists():
        try:
            from ultralytics import YOLO
            model = YOLO(str(YOLO_WEIGHTS))
            method = "yolo-person"
        except Exception:  # pragma: no cover - depends on the local install
            model = None
    elif detector == "yolo":
        raise EditRoomError(f"YOLO weights not found at {YOLO_WEIGHTS}.")
    centres: list[tuple[float, float, float]] = []
    previous = None
    index = 0
    while True:
        ok, frame = capture.read()
        if not ok or frame is None:
            break
        if index % step == 0:
            t = index / fps
            cx = cy = None
            if model is not None:
                result = model.predict(frame, classes=[0], verbose=False, conf=0.35)[0]
                boxes = result.boxes.xyxy.cpu().numpy() if len(result.boxes) else np.zeros((0, 4))
                if len(boxes):
                    areas = (boxes[:, 2] - boxes[:, 0]) * (boxes[:, 3] - boxes[:, 1])
                    weights = areas / areas.sum()
                    cx = float(((boxes[:, 0] + boxes[:, 2]) / 2 * weights).sum())
                    cy = float(((boxes[:, 1] + boxes[:, 3]) / 2 * weights).sum())
            if cx is None:
                small = cv2.resize(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), (width // 8, height // 8))
                if previous is not None:
                    diff = cv2.absdiff(small, previous).astype(np.float32)
                    diff = cv2.GaussianBlur(diff, (0, 0), 3)
                    total = diff.sum()
                    if total > diff.size * 2.0:
                        ys, xs = np.indices(diff.shape)
                        cx = float((xs * diff).sum() / total * 8)
                        cy = float((ys * diff).sum() / total * 8)
                previous = small
            if cx is None:
                cx, cy = width / 2, height / 2
            centres.append((t, cx, cy))
        index += 1
    capture.release()
    if not centres:
        raise EditRoomError(f"No frames decoded from {path.name}.")
    return centres, method


def _smooth_path(centres: list[tuple[float, float, float]], *, crop_w: int, crop_h: int, width: int,
                 height: int, smoothing: float, deadzone: float) -> list[tuple[float, float, float]]:
    """A camera-operator path: dead zone so small moves are ignored, then exponential smoothing."""
    xs = np.array([c[1] for c in centres]); ys = np.array([c[2] for c in centres])
    out_x, out_y = [], []
    px, py = xs[0], ys[0]
    for x, y in zip(xs, ys):
        if abs(x - px) > deadzone * crop_w:
            px += (x - px) * smoothing
        if abs(y - py) > deadzone * crop_h:
            py += (y - py) * smoothing
        out_x.append(px); out_y.append(py)
    kernel = max(1, int(len(out_x) * 0.03) | 1)
    if kernel > 1 and len(out_x) > kernel:
        pad = kernel // 2
        out_x = np.convolve(np.pad(out_x, pad, mode="edge"), np.ones(kernel) / kernel, mode="valid")
        out_y = np.convolve(np.pad(out_y, pad, mode="edge"), np.ones(kernel) / kernel, mode="valid")
    path = []
    for (t, _, _), cx, cy in zip(centres, out_x, out_y):
        x0 = min(max(0.0, cx - crop_w / 2), width - crop_w)
        y0 = min(max(0.0, cy - crop_h / 2), height - crop_h)
        path.append((t, x0, y0))
    return path


def auto_reframe(path: str | Path, output: str | Path, *, aspect: str = "9:16", detector: str = "auto",
                 sample_fps: float = 5.0, smoothing: float = 0.25, deadzone: float = 0.08,
                 encoder: str = "libx264", crf: int = 18, report: str | Path | None = None) -> dict[str, Any]:
    """Tracks the subject and crops landscape footage to `aspect` without upscaling.

    The crop keeps the full source height, so a 1920x1080 source becomes a
    native 608x1080 vertical frame; scale it in the edit only if the delivery
    format requires it. Audio streams are copied unchanged.
    """
    path, output = Path(path), Path(output)
    info = ffprobe_json(path)
    stream = video_stream(info)
    if stream is None:
        raise EditRoomError(f"{path.name} has no video stream.")
    width, height = int(stream["width"]), int(stream["height"])
    fps = frame_rate(info)
    try:
        num, den = (int(v) for v in aspect.split(":"))
    except ValueError as exc:
        raise EditRoomError("aspect must look like 9:16 or 1:1.") from exc
    if num / den >= width / height:
        raise EditRoomError(f"{aspect} is not narrower than the {width}x{height} source; nothing to reframe.")
    crop_w = int(height * num / den) // 2 * 2
    crop_h = height // 2 * 2
    centres, method = _subject_centres(path, width=width, height=height, fps=fps, sample_fps=sample_fps,
                                       detector=detector)
    crop_path = _smooth_path(centres, crop_w=crop_w, crop_h=crop_h, width=width, height=height,
                             smoothing=smoothing, deadzone=deadzone)
    output.parent.mkdir(parents=True, exist_ok=True)
    cmd_file = output.with_suffix(".reframe.cmd")
    lines = []
    for t, x0, y0 in crop_path:
        lines.append(f"{t:.3f} crop x {x0:.1f}, crop y {y0:.1f};")
    cmd_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    sendcmd_path = cmd_file.as_posix().replace(":", "\\:")
    filters = (f"sendcmd=f='{sendcmd_path}',crop=w={crop_w}:h={crop_h}:x={crop_path[0][1]:.1f}:y={crop_path[0][2]:.1f}"
               f",format=yuv420p")
    args = ["-i", str(path), "-map", "0:v:0", "-vf", filters, "-c:v", encoder]
    if encoder == "libx264":
        args += ["-preset", "medium", "-crf", str(crf)]
    elif encoder.endswith("nvenc"):
        args += ["-preset", "p5", "-cq", str(crf), "-b:v", "0"]
    if audio_streams(info):
        args += ["-map", "0:a", "-c:a", "copy"]
    args += ["-movflags", "+faststart", str(output)]
    run_ffmpeg(args)
    cmd_file.unlink(missing_ok=True)
    travel = float(np.abs(np.diff([p[1] for p in crop_path])).sum()) if len(crop_path) > 1 else 0.0
    result = {"source": str(path), "output": str(output), "aspect": aspect, "detector": method,
              "source_size": f"{width}x{height}", "output_size": f"{crop_w}x{crop_h}",
              "samples": len(crop_path), "horizontal_travel_px": round(travel, 1),
              "path": [{"t": round(t, 3), "x": round(x, 1), "y": round(y, 1)} for t, x, y in crop_path],
              "note": "Native crop, no upscale. Check faces and on-screen text stayed inside the frame "
                      "on representative frames before delivery."}
    if report:
        write_json(report, result)
    return result
