"""Scene log: know the footage before writing a word about it.

For one source file this produces ``scene_log.json`` (plus ``SCENE_LOG.md`` and contact sheets):

    scenes[i] = {index, start, end, thumb, kind, energy, hud, characters, description, dialogue: [...]}
    lines[j]  = {start, end, text, speaker, words: [...], scene}

* Cuts come from FFmpeg's scene score on a downscaled copy; long shots are split into beats of at
  most ``max_shot`` seconds so every entry describes one thing.
* Dialogue comes from whisper-1 word timings (the same call the recipes use for narration), grouped
  into lines on punctuation and pauses.
* A vision model looks at one frame per scene and, when a ``subtitle_zone`` is given, at the source's
  own subtitle strip under each line — so a game's or a show's burned-in subtitles become the
  canonical spelling and the speaker label. Whisper mishears names; subtitles do not.

Everything is cached per scene under ``out_dir/scenes`` so a re-run costs nothing. Vision and
transcription are optional (``vision=False``, ``transcribe=False``) for an offline cut-and-thumbnail log.
"""
from __future__ import annotations

import base64
import concurrent.futures
import difflib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

FF = shutil.which("ffmpeg") or "ffmpeg"
FP = shutil.which("ffprobe") or "ffprobe"
VISION_MODEL = os.getenv("DIRECTOR_VISION_MODEL", "gpt-4.1-mini")

VISION_PROMPT = (
    "You are logging footage for a video editor. The first image is one frame of a scene; any further images are crops of the "
    "source's own subtitle strip at the moments people speak in that scene. Return JSON only:\n"
    '{"description": "<one concrete sentence: who is on screen, doing what, where, framing (close-up / wide / over-shoulder)>",'
    ' "characters": ["<names or roles visible>"], "kind": "cutscene|gameplay|graphic|title|other",'
    ' "energy": "low|medium|high", "hud": true|false,'
    ' "subtitles": [{"speaker": "<name before the colon, or empty>", "text": "<subtitle text exactly as written, or empty>"}]}\n'
    "One subtitles entry per strip image, in order. Do not invent a speaker; leave it empty if the strip has no name. "
    "Describe only what is visible."
)


def _run(cmd, **kw):
    p = subprocess.run([str(c) for c in cmd], capture_output=True, text=True, encoding="utf-8", errors="replace", **kw)
    if p.returncode:
        raise RuntimeError(p.stderr[-2000:])
    return p.stdout


def probe(path: Path) -> Dict:
    data = json.loads(_run([FP, "-v", "error", "-show_streams", "-show_format", "-of", "json", path]))
    v = next(s for s in data["streams"] if s["codec_type"] == "video")
    num, den = (v.get("r_frame_rate") or "30/1").split("/")
    return {"duration": float(data["format"]["duration"]), "width": int(v["width"]), "height": int(v["height"]),
            "fps": float(num) / float(den or 1), "codec": v.get("codec_name")}


def scene_cuts(path: Path, threshold: float = 0.30, analysis_width: int = 640) -> List[float]:
    """Hard-cut times via FFmpeg's scene score, measured on a downscaled copy (4K sources take minutes otherwise)."""
    out = subprocess.run([FF, "-hide_banner", "-nostats", "-i", str(path), "-an", "-sn", "-vf",
                          f"scale={analysis_width}:-2,select='gt(scene,{threshold})',metadata=print:file=-", "-f", "null", "-"],
                         capture_output=True, text=True, encoding="utf-8", errors="replace")
    return sorted({round(float(t), 3) for t in re.findall(r"pts_time:([0-9.]+)", out.stdout + out.stderr)})


def scenes_from_cuts(cuts: Sequence[float], duration: float, max_shot: float = 10.0, min_shot: float = 0.4) -> List[Tuple[float, float]]:
    """[start, end) spans: cuts closer than ``min_shot`` merge, spans longer than ``max_shot`` split into equal beats."""
    marks = [0.0]
    for c in cuts:
        if c - marks[-1] >= min_shot and c < duration - min_shot:
            marks.append(c)
    marks.append(duration)
    spans = []
    for a, b in zip(marks, marks[1:]):
        n = max(1, int((b - a) // max_shot) + (1 if (b - a) % max_shot > max_shot * 0.35 else 0))
        step = (b - a) / n
        spans.extend((round(a + k * step, 3), round(a + (k + 1) * step, 3)) for k in range(n))
    return spans


def transcribe(path: Path, work: Path, chunk: float = 1200.0) -> List[Dict]:
    """Word timings for the whole file (whisper-1), in chunks under the API's size limit."""
    from narration_tools import transcribe_words  # noqa: WPS433 (project helper; needs OPENAI_API_KEY)
    meta = probe(path); words: List[Dict] = []
    n = int(meta["duration"] // chunk) + 1
    for k in range(n):
        a = k * chunk; length = min(chunk, meta["duration"] - a)
        if length <= 0.2:
            break
        mp3 = work / f"audio_{k:02}.mp3"; js = work / f"audio_{k:02}.json"
        if not js.exists():
            _run([FF, "-v", "error", "-y", "-ss", a, "-t", length, "-i", path, "-vn", "-ac", 1, "-ar", 16000, "-b:a", "48k", mp3])
            tr = transcribe_words(mp3); js.write_text(json.dumps(tr, ensure_ascii=False), encoding="utf-8")
        tr = json.loads(js.read_text(encoding="utf-8"))
        words.extend(dict(w, start=round(w["start"] + a, 3), end=round(w["end"] + a, 3)) for w in tr["words"])
    return words


def lines_from_words(words: List[Dict], gap: float = 0.8, max_words: int = 40) -> List[Dict]:
    """Group timed words into lines on sentence punctuation and pauses."""
    lines: List[Dict] = []; cur: List[Dict] = []

    def flush():
        if cur:
            lines.append({"start": cur[0]["start"], "end": cur[-1]["end"], "text": " ".join(w["word"] for w in cur), "speaker": "", "words": list(cur)})
            cur.clear()
    for w in words:
        if cur and (w["start"] - cur[-1]["end"] > gap or len(cur) >= max_words):
            flush()
        cur.append(w)
        if re.search(r"[.!?…]$", w["word"]):
            flush()
    flush()
    return lines


def _data_uri(p: Path) -> str:
    return "data:image/jpeg;base64," + base64.b64encode(p.read_bytes()).decode("ascii")


def vision_call(images: List[Path], model: str = VISION_MODEL, cast: str = "") -> Dict:
    import requests
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("OPENAI_API_KEY is required for the vision pass (or run with vision=False)")
    prompt = VISION_PROMPT + (("\nKnown cast (use these names in 'characters' and 'description' when the look matches): " + cast) if cast else "")
    content = [{"type": "text", "text": prompt}] + [{"type": "image_url", "image_url": {"url": _data_uri(p), "detail": "low"}} for p in images]
    r = requests.post("https://api.openai.com/v1/chat/completions", headers={"Authorization": f"Bearer {key}"},
                      json={"model": model, "response_format": {"type": "json_object"}, "temperature": 0.2,
                            "messages": [{"role": "user", "content": content}]}, timeout=120)
    r.raise_for_status()
    return json.loads(r.json()["choices"][0]["message"]["content"])


def _grab(path: Path, t: float, thumb: Path, strip: Optional[Path], zone: Optional[Sequence[float]], thumb_width: int):
    if strip is not None and zone:
        x, y, w, h = zone
        filt = (f"[0:v]split=2[a][b];[a]scale={thumb_width}:-2[t];"
                f"[b]crop=iw*{w}:ih*{h}:iw*{x}:ih*{y},scale=1100:-2[s]")
        _run([FF, "-v", "error", "-y", "-ss", t, "-i", path, "-frames:v", 1, "-filter_complex", filt, "-map", "[t]", thumb, "-map", "[s]", "-frames:v", 1, strip])
    else:
        _run([FF, "-v", "error", "-y", "-ss", t, "-i", path, "-frames:v", 1, "-vf", f"scale={thumb_width}:-2", thumb])


def index_source(path: Path, out_dir: Path, *, label: str = "", subtitle_zone: Optional[Sequence[float]] = None, vision: bool = True,
                 transcribe_audio: bool = True, max_shot: float = 10.0, threshold: float = 0.30, thumb_width: int = 640,
                 workers: int = 4, limit: Optional[int] = None, model: str = VISION_MODEL, cast: str = "", redo_vision: bool = False) -> Dict:
    """Build (or extend) the scene log for one source. ``subtitle_zone`` is (x, y, w, h) as fractions of the frame.

    ``cast`` is a free-text list of who may appear and what they look like, so the log uses names instead of
    "a bearded man in a yellow vest". ``redo_vision`` discards cached descriptions (thumbnails are kept).
    """
    path = Path(path); out_dir = Path(out_dir); scenes_dir = out_dir / "scenes"; scenes_dir.mkdir(parents=True, exist_ok=True)
    meta = probe(path)
    cuts_file = out_dir / "cuts.json"
    if cuts_file.exists():
        cuts = json.loads(cuts_file.read_text(encoding="utf-8"))
    else:
        cuts = scene_cuts(path, threshold); cuts_file.write_text(json.dumps(cuts), encoding="utf-8")
    spans = scenes_from_cuts(cuts, meta["duration"], max_shot=max_shot)
    if limit:
        spans = spans[:limit]
    words = transcribe(path, out_dir, ) if transcribe_audio else []
    lines = lines_from_words(words)
    for i, (a, b) in enumerate(spans):
        for ln in lines:
            mid = (ln["start"] + ln["end"]) / 2
            if a <= mid < b:
                ln["scene"] = i

    def one(item):
        i, (a, b) = item
        rec = scenes_dir / f"{i:04}.json"
        if rec.exists() and not redo_vision:
            return json.loads(rec.read_text(encoding="utf-8"))
        thumb = scenes_dir / f"{i:04}.jpg"
        t = a + min(0.6, (b - a) / 2)
        if not thumb.exists():
            _grab(path, t, thumb, None, None, thumb_width)
        mine = [ln for ln in lines if ln.get("scene") == i]
        strips = []
        if subtitle_zone:
            for k, ln in enumerate(mine[:4]):
                sp = scenes_dir / f"{i:04}_s{k}.jpg"
                if not sp.exists():
                    _grab(path, (ln["start"] + ln["end"]) / 2 + 0.15, scenes_dir / f"{i:04}_tmp.jpg", sp, subtitle_zone, 64)
                strips.append(sp)
            (scenes_dir / f"{i:04}_tmp.jpg").unlink(missing_ok=True)
        info = {"index": i, "start": a, "end": b, "thumb": str(thumb), "kind": "", "energy": "", "hud": None, "characters": [], "description": "", "subtitles": []}
        if vision:
            try:
                v = vision_call([thumb] + strips, model=model, cast=cast)
                info.update({k: v.get(k, info[k]) for k in ("description", "characters", "kind", "energy", "hud")})
                info["subtitles"] = [s for s in v.get("subtitles", []) if isinstance(s, dict)][:len(strips)]
            except Exception as e:  # keep the log; note the failure
                info["description"] = f"(vision failed: {type(e).__name__})"
        rec.write_text(json.dumps(info, ensure_ascii=False, indent=1), encoding="utf-8")
        return info
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        scenes = list(pool.map(one, enumerate(spans)))

    # Attach dialogue to scenes; let the source's own subtitles overrule the transcriber's spelling and name the speaker.
    for sc in scenes:
        sc["dialogue"] = []
    for ln in lines:
        i = ln.get("scene")
        if i is None or i >= len(scenes):
            continue
        sc = scenes[i]
        best, score = None, 0.0
        for sub in sc.get("subtitles", []):
            r = difflib.SequenceMatcher(None, _norm(ln["text"]), _norm(sub.get("text", "")), autojunk=False).ratio()
            if r > score:
                best, score = sub, r
        if best and score >= 0.55 and best.get("text"):
            ln["speaker"] = str(best.get("speaker", "")).strip(); ln["text_source"] = "subtitle"; ln["text"] = best["text"].strip()
        else:
            ln["text_source"] = "transcriber"
        sc["dialogue"].append({k: ln[k] for k in ("start", "end", "text", "speaker")})
    log = {"source": str(path), "label": label or path.stem, "duration": meta["duration"], "fps": meta["fps"], "width": meta["width"], "height": meta["height"],
           "subtitle_zone": list(subtitle_zone) if subtitle_zone else None, "vision_model": model if vision else None, "cast": cast,
           "scenes": scenes, "lines": [{k: v for k, v in ln.items() if k != "words"} | {"words": ln.get("words", [])} for ln in lines]}
    (out_dir / "scene_log.json").write_text(json.dumps(log, ensure_ascii=False, indent=1), encoding="utf-8")
    (out_dir / "SCENE_LOG.md").write_text(markdown(log), encoding="utf-8")
    contact_sheets(log, out_dir)
    return log


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def stamp(t: float) -> str:
    t = int(round(t)); return f"{t//3600:02}:{t//60%60:02}:{t%60:02}"


def markdown(log: Dict) -> str:
    md = [f"# Scene log — {log['label']}", "", f"`{log['source']}` · {stamp(log['duration'])} · {log['width']}×{log['height']} · {log['fps']:.2f} fps", "",
          "| # | time | kind | energy | description | dialogue |", "|---|------|------|--------|-------------|----------|"]
    for sc in log["scenes"]:
        dl = " / ".join((f"**{d['speaker']}:** " if d["speaker"] else "") + d["text"] for d in sc.get("dialogue", []))
        md.append(f"| {sc['index']} | {stamp(sc['start'])}–{stamp(sc['end'])} | {sc.get('kind','')} | {sc.get('energy','')} | {sc.get('description','').replace('|','/')} | {dl.replace('|','/')} |")
    return "\n".join(md) + "\n"


def contact_sheets(log: Dict, out_dir: Path, cols: int = 6, per_sheet: int = 48) -> List[Path]:
    """Thumbnail sheets with index and time, for the human pass that the vision pass does not replace."""
    from PIL import Image, ImageDraw, ImageFont
    try:
        font = ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", 18)
    except OSError:
        font = ImageFont.load_default()
    made = []
    scenes = log["scenes"]
    for s0 in range(0, len(scenes), per_sheet):
        chunk = scenes[s0:s0 + per_sheet]
        thumbs = [Image.open(sc["thumb"]).convert("RGB") for sc in chunk if Path(sc["thumb"]).exists()]
        if not thumbs:
            continue
        w, h = thumbs[0].size; rows = (len(thumbs) + cols - 1) // cols
        sheet = Image.new("RGB", (cols * (w + 4), rows * (h + 4)), "black"); d = ImageDraw.Draw(sheet)
        for k, (sc, im) in enumerate(zip(chunk, thumbs)):
            x, y = (k % cols) * (w + 4), (k // cols) * (h + 4)
            sheet.paste(im.resize((w, h)), (x, y))
            d.rectangle((x, y, x + 150, y + 24), fill="black"); d.text((x + 4, y + 3), f"{sc['index']} · {stamp(sc['start'])}", fill="yellow", font=font)
        p = out_dir / f"sheet_{s0//per_sheet:02}.jpg"; sheet.save(p, quality=80); made.append(p)
    return made


def load(path: Path) -> Dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def find(log: Dict, query: str, *, min_len: float = 0.0, kind: Optional[str] = None, limit: int = 8) -> List[Dict]:
    """Scenes ranked by overlap between the query and description + characters + dialogue."""
    from .story import key_tokens
    q = key_tokens(query); qn = _norm(query)
    out = []
    for sc in log["scenes"]:
        if sc["end"] - sc["start"] < min_len or (kind and sc.get("kind") != kind):
            continue
        hay = " ".join([sc.get("description", ""), " ".join(sc.get("characters", []))] + [d["text"] + " " + d.get("speaker", "") for d in sc.get("dialogue", [])])
        toks = key_tokens(hay)
        score = len(q & toks) + (2 if qn and qn in _norm(hay) else 0)
        if score:
            out.append((score, sc))
    out.sort(key=lambda x: (-x[0], x[1]["start"]))
    return [dict(sc, score=s) for s, sc in out[:limit]]


def resolve(log: Dict, query: str, *, min_len: float = 0.0) -> Optional[float]:
    """The start time of the best-matching scene, for recipes that plan shots by meaning."""
    hits = find(log, query, min_len=min_len, limit=1)
    return hits[0]["start"] if hits else None
