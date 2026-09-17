"""Shared helpers for the ``create_*`` recipes: cached Cedar takes with word timings,
silence tightening, envelope-based caption re-timing, cue grouping and SRT output.

Extracted unchanged from the Elden Ring recipe (2026-09-14) so later builds reuse one
copy. Nothing here stretches or pitch-shifts speech; ``tighten`` only shortens measured
silences between sentences (AGENTS.md).
"""
import difflib
import hashlib
import json
import os
import re
import shutil
import subprocess
import time
import wave
from pathlib import Path

import numpy as np
import requests

from narration_tools import synthesize, transcribe_words, restore_punctuation

FF = shutil.which("ffmpeg") or "ffmpeg"
FP = shutil.which("ffprobe") or "ffprobe"


def run(cmd, cwd=None):
    p = subprocess.run([str(v) for v in cmd], cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if p.returncode:
        raise RuntimeError(p.stderr[-4000:])
    return p.stdout


def norm(s):
    return re.sub("[^a-z0-9]", "", s.lower())


def wav_seconds(p):
    with wave.open(str(p), "rb") as f:
        return f.getnframes() / f.getframerate()


def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# --- Narration takes --------------------------------------------------------------
def tighten(source, words, dest):
    """Shorten measured silences inside a take; never touches speech (AGENTS.md)."""
    with wave.open(str(source), "rb") as f:
        params = f.getparams(); raw = f.readframes(f.getnframes())
    rate = params.framerate; stride = params.sampwidth * params.nchannels; dur = len(raw) / stride / rate
    assert params.sampwidth == 2
    samples = np.frombuffer(raw, dtype=np.int16).reshape(-1, params.nchannels).astype(np.float32)
    win = round(rate * .01); pad = (-len(samples)) % win
    energy = np.sqrt(np.mean(np.pad(samples, ((0, pad), (0, 0))).reshape(-1, win, params.nchannels) ** 2, axis=(1, 2))) / 32768
    quiet = energy < 10 ** (-39 / 20); spans = []; start = None
    for i, q in enumerate(list(quiet) + [False]):
        if q and start is None:
            start = i * .01
        if not q and start is not None:
            if i * .01 - start > .16:
                spans.append((start, min(dur, i * .01)))
            start = None
    cuts = []
    for a, b in spans:
        if a < .02:
            end = b - .055
            if end > .02:
                cuts.append((0, end))
        elif b > dur - .025:
            begin = max(a + .075, words[-1]["end"] + .09)
            if begin < dur:
                cuts.append((begin, dur))
        else:
            gap = next(((l["end"], r["start"]) for l, r in zip(words, words[1:]) if l["end"] <= a + .08 and r["start"] >= b - .08), None)
            if gap and b - a > .47:
                left = a + .16; right = b - .16
                if right > left:
                    cuts.append((left, right))
    result = bytearray(); last = 0; canonical = []
    for a, b in cuts:
        a = round(a * rate); b = round(b * rate)
        result += raw[last * stride:a * stride]; last = b; canonical.append((a / rate, b / rate))
    result += raw[last * stride:]

    def shift(t):
        return t - sum(max(0, min(t, b) - a) for a, b in canonical if t > a)
    fixed = [dict(w, start=round(shift(w["start"]), 3), end=round(max(shift(w["start"]) + .02, shift(w["end"])), 3)) for w in words]
    with wave.open(str(dest), "wb") as f:
        f.setparams(params._replace(nframes=len(result) // stride)); f.writeframes(result)
    return {"words": fixed, "seconds": len(result) / stride / rate, "original_seconds": dur, "removed": canonical}


def narrate_cached(text, dest, preset):
    """Synthesize + transcribe once; a take whose WAV exists is never re-recorded."""
    dest = Path(dest); meta = dest.with_suffix(".json")
    if dest.exists() and meta.exists():
        return json.loads(meta.read_text(encoding="utf-8"))
    for attempt in range(4):
        try:
            if not dest.exists():
                synthesize(text, dest, preset)
            tr = transcribe_words(dest)
            break
        except Exception as e:
            if attempt == 3:
                raise
            print(f"retry {dest.name}: {type(e).__name__}", flush=True); time.sleep(4 * (attempt + 1))
    duration = wav_seconds(dest)
    data = {"text": text, "audio": str(dest), "duration": round(duration, 3), "words": restore_punctuation(tr["words"], text), "heard": tr["text"]}
    meta.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    return data


def second_opinion(path):
    """Text-only transcription with a second model, used to confirm a take's ending."""
    key = os.getenv("OPENAI_API_KEY")
    with open(path, "rb") as f:
        r = requests.post("https://api.openai.com/v1/audio/transcriptions", headers={"Authorization": f"Bearer {key}"},
                          files={"file": (Path(path).name, f, "audio/wav")}, data={"model": "gpt-4o-transcribe", "response_format": "json", "language": "en"}, timeout=300)
    r.raise_for_status(); return r.json().get("text", "")


_UNITS = {w: i for i, w in enumerate("zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen".split())}
_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90}


def numify(tokens):
    """Spell number words as digits ("thirty nine" -> "39") so a transcriber's numerals compare equal."""
    out = []; i = 0
    while i < len(tokens):
        t = tokens[i]
        if t in _TENS and i + 1 < len(tokens) and tokens[i + 1] in _UNITS and 0 < _UNITS[tokens[i + 1]] < 10:
            out.append(str(_TENS[t] + _UNITS[tokens[i + 1]])); i += 2; continue
        out.append(str(_TENS[t]) if t in _TENS else (str(_UNITS[t]) if t in _UNITS else t)); i += 1
    return out


def ending_check(wav, text, heard):
    """Cedar sometimes drops a short final clause (memory: cedar-tts-drops-final-clause)."""
    want = numify(re.findall("[a-z0-9]+", text.lower()))[-4:]; got = numify(re.findall("[a-z0-9]+", heard.lower()))
    if got[-4:] == want or (len(got) >= 2 and got[-2:] == want[-2:]):
        return {"ending_ok": True, "checked_with": "whisper-1"}
    second = second_opinion(wav); got2 = numify(re.findall("[a-z0-9]+", second.lower()))
    ok = got2[-4:] == want or (len(got2) >= 2 and got2[-2:] == want[-2:])
    return {"ending_ok": ok, "checked_with": "gpt-4o-transcribe", "second_text": second}


def take_report(name, text, audio_dir, preset):
    """Record (or reuse) one take, tighten it, and return the report written next to it."""
    audio_dir = Path(audio_dir)
    data = narrate_cached(text, audio_dir / (name + ".wav"), preset)
    tight = tighten(audio_dir / (name + ".wav"), data["words"], audio_dir / (name + ".tight.wav"))
    tokens = re.findall("[a-z0-9]+", text.lower()); heard = re.findall("[a-z0-9]+", data.get("heard", "").lower())
    sm = difflib.SequenceMatcher(None, tokens, heard, autojunk=False)
    agreement = sm.ratio()
    diffs = [{"expected": tokens[a:b], "heard": heard[c:d]} for tag, a, b, c, d in sm.get_opcodes() if tag != "equal"]
    ending = ending_check(audio_dir / (name + ".wav"), text, data.get("heard", ""))
    report = {"name": name, "text": text, "seconds": round(tight["seconds"], 3), "original_seconds": round(tight["original_seconds"], 3),
              "removed_seconds": round(tight["original_seconds"] - tight["seconds"], 3), "cuts": tight["removed"], "agreement": round(agreement, 3),
              "differences": diffs, **ending, "words": tight["words"]}
    (audio_dir / (name + ".tight.json")).write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")
    return report


# --- Word timing --------------------------------------------------------------------
def anchor_time(words, phrase):
    if not phrase:
        return 0.0
    target = norm(phrase); flat = [norm(w["word"]) for w in words]
    for i in range(len(flat)):
        acc = ""
        for k in range(i, len(flat)):
            acc += flat[k]
            if acc == target:
                return words[i]["start"]
            if len(acc) >= len(target) or not target.startswith(acc):
                break
    raise ValueError(f"No anchor {phrase!r}")


def script_words(words, text):
    """Timed words spelled as the script spells them; dropped words get interpolated times."""
    tokens = text.split(); out = []
    sm = difflib.SequenceMatcher(None, [norm(w["word"]) for w in words], [norm(t) for t in tokens], autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            out.extend(dict(word=tokens[j1 + k], start=words[i1 + k]["start"], end=words[i1 + k]["end"]) for k in range(i2 - i1))
        elif tag == "replace":
            a = words[i1]["start"]; b = words[i2 - 1]["end"]; n = j2 - j1
            out.extend(dict(word=tokens[j1 + k], start=round(a + (b - a) * k / n, 3), end=round(a + (b - a) * (k + 1) / n, 3)) for k in range(n))
        elif tag == "insert":
            a = out[-1]["end"] if out else 0.0; b = words[i1]["start"] if i1 < len(words) else a + 0.3 * (j2 - j1)
            n = j2 - j1; b = max(b, a + 0.12 * n)
            out.extend(dict(word=tokens[j1 + k], start=round(a + (b - a) * k / n, 3), end=round(a + (b - a) * (k + 1) / n, 3)) for k in range(n))
    for i, w in enumerate(out):
        if not norm(w["word"]):
            nxt = next((x for x in out[i + 1:] if norm(x["word"])), None)
            t = nxt["start"] if nxt else w["end"]; w["start"] = w["end"] = t
    return out


def _syllables(word):
    w = re.sub(r"[^a-z0-9]", "", word.lower())
    if not w:
        return 0.3
    if w.isdigit():
        return max(1, len(w))
    groups = len(re.findall(r"[aeiouy]+", w))
    if w.endswith("e") and not w.endswith(("le", "ee", "ye")) and groups > 1:
        groups -= 1
    return max(1, groups)


def retime_words(words, env, step, blend=0.6):
    """Re-time transcriber words against measured speech runs (see V2 recipe)."""
    if not words:
        return words
    n = len(env); quiet = np.ones(n, dtype=bool)
    for i in range(0, n, 200):
        seg = env[max(0, i - 200):i + 400]
        thr = max(10 ** (-38 / 20), 0.22 * float(np.percentile(seg, 90)) if len(seg) else 0)
        quiet[i:i + 200] = env[i:i + 200] < thr
    runs, start = [], None
    for i, q in enumerate(list(quiet) + [True]):
        if not q and start is None:
            start = i
        if q and start is not None:
            if (i - start) * step >= 0.06:
                if runs and (start - runs[-1][1]) * step < 0.12:
                    runs[-1] = (runs[-1][0], i)
                else:
                    runs.append((start, i))
            start = None
    if not runs:
        return words
    spans = [(a * step, b * step) for a, b in runs]
    assign = []; last = 0
    for w in words:
        m = (w["start"] + w["end"]) / 2
        k = next((i for i, (a, b) in enumerate(spans) if a - 0.05 <= m <= b + 0.05), None)
        if k is None:
            k = min(range(len(spans)), key=lambda i: min(abs(spans[i][0] - m), abs(spans[i][1] - m)))
        k = max(k, last); assign.append(k); last = k
    out = [dict(w) for w in words]
    for k, (ra, rb) in enumerate(spans):
        idx = [i for i, g in enumerate(assign) if g == k]
        if not idx:
            continue
        first_ws, last_we = words[idx[0]]["start"], words[idx[-1]]["end"]
        a = ra if abs(first_ws - ra) < 0.35 else max(ra, first_ws - 0.15)
        b = rb if abs(last_we - rb) < 0.35 else min(rb, last_we + 0.15)
        if b - a < 0.1:
            continue
        weights = [_syllables(words[i]["word"]) + 0.35 for i in idx]; total = sum(weights); pos = a
        for n2, (i, wt) in enumerate(zip(idx, weights)):
            ps, pe = pos, pos + (b - a) * wt / total; pos = pe
            ws, we = words[i]["start"], words[i]["end"]
            st = a if (n2 == 0 and a == ra) else blend * ps + (1 - blend) * ws
            en = b if (n2 == len(idx) - 1 and b == rb) else blend * pe + (1 - blend) * we
            out[i]["start"] = round(min(max(st, a), b), 3)
            out[i]["end"] = round(min(max(en, out[i]["start"] + 0.04), b + 0.02), 3)
    for i in range(1, len(out)):
        if out[i]["start"] < out[i - 1]["end"] - 0.02:
            out[i]["start"] = round(out[i - 1]["end"] - 0.02, 3)
            out[i]["end"] = max(out[i]["end"], out[i]["start"] + 0.04)
    return out


def speech_envelope(path, step=0.01):
    """RMS envelope in `step`-second windows. Decodes through ffmpeg so 24-bit / extensible
    WAV masters work on every Python version (the wave module rejects them before 3.12)."""
    raw = subprocess.run([FF, "-v", "error", "-i", str(path), "-f", "s16le", "-ac", "1", "-ar", "48000", "-"], capture_output=True, check=True).stdout
    x = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768
    win = int(48000 * step); n = len(x) // win
    return np.sqrt((x[:n * win] ** 2).reshape(n, win).mean(axis=1)), step


# --- Captions ---------------------------------------------------------------------------
def stamp(t):
    n = round(t * 100); return f"{n//360000}:{n//6000%60:02}:{n//100%60:02}.{n%100:02}"


def ass_escape(t):
    return t.replace("\\", "\\\\").replace("{", "(").replace("}", ")")


def group_words(words, max_words, max_chars):
    cues, cur = [], []
    for w in words:
        if cur and (w.get("unit") != cur[-1].get("unit") or len(cur) >= max_words or len(" ".join(x["word"] for x in cur + [w])) > max_chars):
            cues.append(cur); cur = []
        cur.append(w)
        if re.search(r"[.!?…]$", w["word"]) or (re.search(r"[,;:]$", w["word"]) and len(cur) >= max_words - 2):
            cues.append(cur); cur = []
    if cur:
        cues.append(cur)
    out = []
    for c in cues:
        a = c[0]["start"]; b = max(c[-1]["end"], a + 0.6)
        out.append((a, b, " ".join(x["word"] for x in c), c[0].get("unit")))
    for i in range(len(out) - 1):
        if out[i][1] > out[i + 1][0]:
            out[i] = (out[i][0], out[i + 1][0], out[i][2], out[i][3])
    return out


def _quiet_mask(env, step, t, thr_db=-38.0, local=2.0):
    i0 = max(0, int((t - local) / step)); i1 = min(len(env), int((t + local) / step) + 1)
    seg = env[i0:i1]
    thr = max(10 ** (thr_db / 20), 0.25 * float(np.percentile(seg, 90)) if len(seg) else 0)
    return env < thr


def snap(t, env, step, kind, window=0.45):
    quiet = _quiet_mask(env, step, t)
    i = int(round(t / step)); r = int(window / step); best = None
    for d in range(0, r + 1):
        for j in (i - d, i + d):
            if 1 <= j < len(quiet):
                edge = (quiet[j - 1] and not quiet[j]) if kind == "start" else (not quiet[j - 1] and quiet[j])
                if edge:
                    best = j; break
        if best is not None:
            break
    if best is None:
        return t
    return round(best * step - (0.03 if kind == "start" else -0.02), 3)


def snap_cues(cues, env, step):
    out = []
    for a, b, text, unit in cues:
        out.append([snap(a, env, step, "start"), snap(b, env, step, "end"), text, unit])
    for i in range(len(out)):
        if i + 1 < len(out):
            out[i][1] = min(out[i][1], out[i + 1][0] - 0.02)
        out[i][1] = max(out[i][1], out[i][0] + 0.4)
        if i + 1 < len(out) and out[i][1] > out[i + 1][0]:
            out[i + 1][0] = out[i][1] + 0.02
    return [tuple(c) for c in out]


def srt_stamp(t):
    ms = round(t * 1000); return f"{ms//3600000:02}:{ms//60000%60:02}:{ms//1000%60:02},{ms%1000:03}"


def srt_from(cues):
    return "\n".join(f"{i}\n{srt_stamp(a)} --> {srt_stamp(b)}\n{text}\n" for i, (a, b, text, unit) in enumerate(cues, 1))


# --- Encoding -------------------------------------------------------------------------------
def nvenc_available():
    try:
        run([FF, "-v", "error", "-f", "lavfi", "-i", "testsrc=size=64x64:rate=30", "-frames:v", 2, "-c:v", "h264_nvenc", "-f", "null", "-"])
        return True
    except RuntimeError:
        return False
