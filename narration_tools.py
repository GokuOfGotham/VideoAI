"""Narration and word-timing helpers shared by the ``create_*`` recipes.

Voice: ``APPROVED_VOICE_PRESET.json`` (OpenAI ``gpt-4o-mini-tts``, Cedar, with
the saved delivery direction) is the default for new videos — see AGENTS.md.
Word timings come from OpenAI's transcription API: faster-whisper is not
installed in this environment, and the length-estimate fallback in
``voice_synthesizer`` drifts too far for word-highlight captions.
"""

import difflib
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Dict, List

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

PROJECT_ROOT = Path(__file__).resolve().parent
PRESET_FILE = PROJECT_ROOT / "APPROVED_VOICE_PRESET.json"

_TRAILING = re.compile(r"[.!?,;:…]+[\"'’”)]*$")


def _key() -> str:
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("OPENAI_API_KEY is required for narration and word timings.")
    return key


def load_preset() -> Dict:
    with open(PRESET_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def synthesize(text: str, dest: Path, preset: Dict = None) -> Path:
    """Reads `text` with the approved preset and masters it with its filter.

    The finished take is never stretched or pitch-shifted to fit an edit;
    rewrite the line instead (AGENTS.md).
    """
    preset = preset or load_preset()
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    resp = requests.post(
        "https://api.openai.com/v1/audio/speech",
        headers={"Authorization": f"Bearer {_key()}", "Content-Type": "application/json"},
        json={
            "model": preset.get("model", "gpt-4o-mini-tts"),
            "voice": preset.get("voice", "cedar"),
            "speed": preset.get("speed", 1.0),
            "input": text,
            "instructions": preset.get("instructions", ""),
            "response_format": "wav",
        },
        timeout=180,
    )
    resp.raise_for_status()
    raw = dest.with_suffix(".raw.wav")
    raw.write_bytes(resp.content)
    subprocess.run([
        "ffmpeg", "-y", "-v", "error", "-i", str(raw),
        "-af", preset.get("mastering_filter", "highpass=f=70,loudnorm=I=-16:TP=-2:LRA=9"),
        "-ar", "48000", "-ac", "2", str(dest),
    ], check=True)
    raw.unlink(missing_ok=True)
    return dest


def transcribe_words(audio_path: Path, language: str = "en") -> Dict:
    """Word-level timings plus the punctuated text, from OpenAI's transcription."""
    audio_path = Path(audio_path)
    mime = "audio/wav" if audio_path.suffix.lower() == ".wav" else "audio/mpeg"
    with open(audio_path, "rb") as f:
        resp = requests.post(
            "https://api.openai.com/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {_key()}"},
            files={"file": (audio_path.name, f, mime)},
            data={"model": "whisper-1", "response_format": "verbose_json",
                  "timestamp_granularities[]": "word", "language": language},
            timeout=300,
        )
    resp.raise_for_status()
    data = resp.json()
    words = [{"word": w["word"].strip(), "start": round(float(w["start"]), 3),
              "end": round(float(w["end"]), 3)}
             for w in data.get("words") or [] if w.get("word", "").strip()]
    return {"text": data.get("text", ""), "words": sanitise(words)}


def sanitise(words: List[Dict]) -> List[Dict]:
    """Gives zero-length words a span; the transcriber emits a few per take."""
    out = []
    for i, w in enumerate(words):
        start, end = float(w["start"]), float(w["end"])
        if end <= start:
            limit = float(words[i + 1]["start"]) if i + 1 < len(words) else start + 0.35
            end = max(start + 0.05, min(start + 0.3, limit))
        out.append({**w, "start": round(start, 3), "end": round(end, 3)})
    return out


def bare(word: str) -> str:
    return re.sub(r"[^a-z0-9]", "", word.lower())


def restore_punctuation(words: List[Dict], script: str) -> List[Dict]:
    """Carries a script's punctuation onto the transcript's timed words.

    The transcription's word list is bare; the caption engine groups phrases
    on punctuation, so without it every caption runs on. The two are aligned
    as sequences, so a spelled-out number matched against its digits, or a
    compound the transcriber split, still ends up with its sentence break.
    Em-dash clauses become comma breaks.
    """
    tokens = script.replace(" — ", ", ").replace("—", ", ").split()
    out = [dict(w) for w in words]
    matcher = difflib.SequenceMatcher(
        None, [bare(w["word"]) for w in words], [bare(t) for t in tokens], autojunk=False
    )
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for i, j in zip(range(i1, i2), range(j1, j2)):
                out[i]["word"] = tokens[j]
        elif tag == "replace" and (i2 - i1) == (j2 - j1):
            # Same number of words, spelled differently ("Nightfall" for
            # "Knightfall"): the script is what was read, so use it.
            for i, j in zip(range(i1, i2), range(j1, j2)):
                out[i]["word"] = tokens[j]
        elif tag == "replace" and i2 > i1 and j2 > j1:
            # Different word count for the same stretch ("lift off" for
            # "Liftoff."): keep the transcript's words, borrow the punctuation
            # that closes the script's.
            trailing = _TRAILING.search(tokens[j2 - 1])
            if trailing and not re.search(r"[.!?,;:…]$", out[i2 - 1]["word"]):
                out[i2 - 1]["word"] += trailing.group(0)
    return out


def locate(words: List[Dict], target: str, start: int = 0) -> int:
    """Index of the transcript word spelling `target`, searching forward.

    Transcribers split compounds unpredictably ("lift off"), so a target may
    also be matched across two adjacent words.
    """
    want = bare(target)
    for i in range(start, len(words)):
        if bare(words[i]["word"]) == want:
            return i
        if i + 1 < len(words) and bare(words[i]["word"]) + bare(words[i + 1]["word"]) == want:
            return i + 1
    raise RuntimeError(f"Could not find '{target}' in the transcript")


def narrate_line(text: str, dest: Path, preset: Dict = None) -> Dict:
    """Synthesizes one line and returns its path, duration, and timed words.

    Cached next to the audio, so rebuilding an edit never re-records a take
    (and never changes a delivery the user has already heard).
    """
    dest = Path(dest)
    meta = dest.with_suffix(".json")
    if dest.exists() and meta.exists():
        return json.loads(meta.read_text(encoding="utf-8"))
    synthesize(text, dest, preset)
    tr = transcribe_words(dest)
    duration = float(subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(dest)], capture_output=True, text=True).stdout.strip() or 0)
    data = {"text": text, "audio": str(dest), "duration": round(duration, 3),
            "words": restore_punctuation(tr["words"], text)}
    meta.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    return data
