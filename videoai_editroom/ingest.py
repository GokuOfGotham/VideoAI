"""Assistant editor: transcription, multicam sync, silence/filler detection, proxies.

Transcription runs locally with faster-whisper (word timestamps) or, when
``engine="openai"``, through the same OpenAI transcription the narration
tools use. Speaker labels are heuristic turn detection from pauses and pitch
unless a real diarisation backend is supplied through ``diarizer``; the
report says which was used so nobody mistakes a guess for identification.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable, Iterable

import numpy as np

from .common import (EditRoomError, decode_mono, ffprobe_json, media_duration, run_ffmpeg,
                     timecode, video_stream, write_json)

FILLER_WORDS = {"um", "uh", "er", "ah", "hmm", "mm", "like", "youknow", "sortof", "kindof",
                "basically", "literally", "actually"}
_SILENCE_START = re.compile(r"silence_start:\s*([0-9.]+)")
_SILENCE_END = re.compile(r"silence_end:\s*([0-9.]+)\s*\|\s*silence_duration:\s*([0-9.]+)")


# --- TranscribeMedia ----------------------------------------------------------


def _whisper_words(path: Path, language: str, model_size: str, device: str) -> tuple[str, list[dict[str, Any]], str]:
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise EditRoomError("faster-whisper is not installed; use engine='openai' or install it.") from exc
    words: list[dict[str, Any]] = []
    text_parts = []
    devices = [("cuda", "float16"), ("cpu", "int8")] if device == "auto" else [(device, "auto")]
    last_error: Exception | None = None
    for name, compute in devices:
        try:
            model = WhisperModel(model_size, device=name, compute_type=compute)
            segments, _ = model.transcribe(str(path), language=language, word_timestamps=True,
                                           vad_filter=True)
            for segment in segments:
                text_parts.append(segment.text.strip())
                for word in segment.words or []:
                    token = word.word.strip()
                    if token:
                        words.append({"word": token, "start": round(float(word.start), 3),
                                      "end": round(float(word.end), 3),
                                      "confidence": round(float(word.probability), 3)})
            return " ".join(text_parts), words, name
        except (RuntimeError, ValueError, OSError) as exc:
            # A GPU build without its CUDA runtime raises here; fall back to the CPU.
            last_error = exc
            words.clear()
            text_parts.clear()
    raise EditRoomError(f"faster-whisper could not transcribe {path.name}: {last_error}")


def _openai_words(path: Path, language: str) -> tuple[str, list[dict[str, Any]]]:
    from narration_tools import transcribe_words
    data = transcribe_words(path, language=language)
    return data["text"], data["words"]


def _heuristic_speakers(words: list[dict[str, Any]], path: Path, turn_gap: float) -> list[str]:
    """Labels a new speaker at long pauses when the voice pitch band changes.

    Sentence-internal pauses keep the speaker; a pause longer than `turn_gap`
    combined with a shift in the dominant pitch band starts a new label. It is
    a placeholder for real diarisation, and the report flags it as such.
    """
    if not words:
        return []
    rate = 8000
    try:
        samples = decode_mono(path, rate)
    except EditRoomError:
        samples = np.zeros(1, dtype=np.float32)

    def pitch_band(start: float, end: float) -> float:
        a, b = int(start * rate), int(end * rate)
        chunk = samples[a:b]
        if chunk.size < rate // 20:
            return 0.0
        spectrum = np.abs(np.fft.rfft(chunk * np.hanning(chunk.size)))
        freqs = np.fft.rfftfreq(chunk.size, 1 / rate)
        band = (freqs >= 70) & (freqs <= 400)
        if not band.any() or spectrum[band].sum() == 0:
            return 0.0
        return float((freqs[band] * spectrum[band]).sum() / spectrum[band].sum())

    labels, speaker = [], 1
    current_pitch = None
    turn_start = words[0]["start"]
    for index, word in enumerate(words):
        if index and word["start"] - words[index - 1]["end"] >= turn_gap:
            pitch = pitch_band(turn_start, words[index - 1]["end"])
            if current_pitch is None:
                current_pitch = pitch
            new_pitch = pitch_band(word["start"], min(word["start"] + 2.0, words[-1]["end"]))
            if current_pitch and new_pitch and abs(new_pitch - current_pitch) / current_pitch > 0.18:
                speaker += 1
                current_pitch = new_pitch
            turn_start = word["start"]
        labels.append(f"SPEAKER_{speaker}")
    return labels


def _segments_from_words(words: list[dict[str, Any]], speakers: list[str], max_gap: float = 0.8,
                         max_words: int = 24) -> list[dict[str, Any]]:
    segments: list[dict[str, Any]] = []
    for word, speaker in zip(words, speakers):
        current = segments[-1] if segments else None
        starts_new = (current is None or current["speaker"] != speaker
                      or word["start"] - current["end"] > max_gap
                      or len(current["words"]) >= max_words
                      or re.search(r"[.!?]$", current["words"][-1]["word"]))
        if starts_new:
            segments.append({"speaker": speaker, "start": word["start"], "end": word["end"],
                             "words": [word]})
        else:
            current["words"].append(word)
            current["end"] = word["end"]
    for segment in segments:
        segment["text"] = " ".join(w["word"] for w in segment["words"])
    return segments


def transcribe_media(path: str | Path, *, language: str = "en", engine: str = "whisper",
                     model_size: str = "small", diarizer: Callable[[Path, list[dict]], list[str]] | None = None,
                     turn_gap: float = 1.0, output: str | Path | None = None,
                     fps: float = 30.0, device: str = "auto") -> dict[str, Any]:
    """Timecoded transcript with words, sentence segments and speaker labels.

    ``device`` is auto (GPU when its runtime is present, else CPU), cuda or cpu.
    """
    path = Path(path)
    if not path.exists():
        raise EditRoomError(f"Media not found: {path}")
    backend = engine
    if engine == "whisper":
        text, words, used = _whisper_words(path, language, model_size, device)
        backend = f"faster-whisper/{model_size}/{used}"
    elif engine == "openai":
        text, words = _openai_words(path, language)
    else:
        raise EditRoomError(f"Unknown transcription engine '{engine}' (whisper or openai).")
    if diarizer is not None:
        speakers = list(diarizer(path, words))
        method = "diarizer"
        if len(speakers) != len(words):
            raise EditRoomError("The diarizer must return one speaker label per word.")
    else:
        speakers = _heuristic_speakers(words, path, turn_gap)
        method = "heuristic-turns"
    for word, speaker in zip(words, speakers):
        word["speaker"] = speaker
    segments = _segments_from_words(words, speakers)
    for segment in segments:
        segment["timecode"] = timecode(segment["start"], fps)
    report = {"source": str(path), "engine": backend, "language": language,
              "speaker_method": method,
              "speaker_note": ("Labels are pause/pitch heuristics, not identification; name "
                               "speakers from the footage before putting them on screen.")
              if method == "heuristic-turns" else "Labels supplied by the diarizer.",
              "text": text.strip(), "word_count": len(words), "words": words,
              "segments": segments,
              "speakers": sorted({s for s in speakers}, key=lambda s: int(s.rsplit("_", 1)[-1])
                                 if s.rsplit("_", 1)[-1].isdigit() else 0)}
    if output:
        write_json(output, report)
        report["output"] = str(output)
    return report


# --- SyncMulticam -------------------------------------------------------------


def _envelope(samples: np.ndarray, rate: int, hop: int) -> np.ndarray:
    frames = samples.size // hop
    if frames == 0:
        raise EditRoomError("Audio is too short to align.")
    env = np.abs(samples[: frames * hop]).reshape(frames, hop).mean(axis=1)
    env = env - env.mean()
    norm = np.linalg.norm(env)
    return env / norm if norm else env


def audio_offset(reference: str | Path, other: str | Path, *, rate: int = 8000, hop: int = 80,
                 window: float | None = 600.0) -> dict[str, Any]:
    """Seconds `other` must be shifted so its audio lines up with `reference`.

    Cross-correlates loudness envelopes (10 ms hops at the default rate), which
    is robust to different microphones and gains. A positive offset means the
    same sound arrives that much later in `other` than in `reference`: trim
    that much from the head of `other` (or slide it left) to conform.
    """
    ref = _envelope(decode_mono(reference, rate, duration=window), rate, hop)
    oth = _envelope(decode_mono(other, rate, duration=window), rate, hop)
    size = 1
    while size < ref.size + oth.size:
        size *= 2
    corr = np.fft.irfft(np.fft.rfft(ref, size) * np.conj(np.fft.rfft(oth, size)), size)
    lag = int(np.argmax(corr))
    if lag > size // 2:
        lag -= size
    peak = float(corr[int(np.argmax(corr))])
    rest = np.delete(corr, int(np.argmax(corr)))
    confidence = float(peak / (np.abs(rest).mean() * 8 + 1e-9))
    return {"offset_seconds": round(-lag * hop / rate, 3), "confidence": round(min(confidence, 1.0), 3)}


def sync_multicam(reference: str | Path, angles: Iterable[str | Path], *, output: str | Path | None = None,
                  fps: float | None = None, min_confidence: float = 0.35) -> dict[str, Any]:
    """Aligns every angle and external audio track to the reference by waveform."""
    reference = Path(reference)
    info = ffprobe_json(reference)
    from .common import frame_rate
    fps = fps or frame_rate(info)
    results = []
    for angle in angles:
        angle = Path(angle)
        found = audio_offset(reference, angle)
        results.append({"file": str(angle), **found,
                        "offset_frames": int(round(found["offset_seconds"] * fps)),
                        "offset_timecode": timecode(abs(found["offset_seconds"]), fps),
                        "reliable": found["confidence"] >= min_confidence,
                        "kind": "audio" if video_stream(ffprobe_json(angle)) is None else "video"})
    report = {"reference": str(reference), "fps": fps, "angles": results,
              "unreliable": [r["file"] for r in results if not r["reliable"]],
              "note": "A positive offset means the angle runs that many seconds behind the reference: "
                      "trim it from the angle's head to conform. Confirm low-confidence angles on a clap."}
    if output:
        write_json(output, report)
    return report


# --- DetectSilence ------------------------------------------------------------


def _content_words(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9']+", text.lower()) if w not in FILLER_WORDS]


def _is_retake(first: list[str], second: list[str], min_words: int = 3) -> bool:
    """True when the next segment restarts the same opening words: a flubbed take."""
    if len(first) < min_words or len(second) < min_words:
        return False
    head = first[:max(min_words, len(first) * 2 // 3)]
    for offset in range(0, len(second) - len(head) + 1):
        if second[offset:offset + len(head)] == head:
            return True
    return False


def detect_silence(path: str | Path, *, noise_db: float = -35.0, min_duration: float = 0.6,
                   transcript: dict[str, Any] | None = None, keep_pause: float = 0.25,
                   output: str | Path | None = None) -> dict[str, Any]:
    """Dead air, filler words and retakes as timecoded cut candidates.

    Silences come from FFmpeg's silencedetect. With a transcript (from
    ``transcribe_media``) fillers and immediate repeats of the same phrase
    (retakes) are also listed. Every range is a candidate, not an order: the
    policy keeps pauses that carry tension, so the editor decides per range.
    """
    path = Path(path)
    total = media_duration(path)
    log = run_ffmpeg(["-i", str(path), "-map", "0:a:0", "-af",
                      f"silencedetect=noise={noise_db}dB:d={min_duration}", "-f", "null", "-"])
    starts = [float(m.group(1)) for m in _SILENCE_START.finditer(log)]
    ends = [(float(m.group(1)), float(m.group(2))) for m in _SILENCE_END.finditer(log)]
    silences = []
    for index, start in enumerate(starts):
        end = ends[index][0] if index < len(ends) else total
        cut_in, cut_out = start + keep_pause / 2, end - keep_pause / 2
        if cut_out - cut_in >= 0.1:
            silences.append({"type": "silence", "start": round(start, 3), "end": round(end, 3),
                             "cut_in": round(cut_in, 3), "cut_out": round(cut_out, 3),
                             "duration": round(end - start, 3)})
    fillers, retakes = [], []
    if transcript:
        words = transcript.get("words", [])
        for word in words:
            bare = re.sub(r"[^a-z]", "", word["word"].lower())
            if bare in FILLER_WORDS and bare not in {"like", "actually", "basically", "literally"}:
                fillers.append({"type": "filler", "word": word["word"], "start": word["start"],
                                "end": word["end"]})
        phrases = [(_content_words(s.get("text", "")), s) for s in transcript.get("segments", [])]
        for (words_a, seg_a), (words_b, seg_b) in zip(phrases, phrases[1:]):
            if _is_retake(words_a, words_b):
                retakes.append({"type": "retake", "start": seg_a["start"], "end": seg_a["end"],
                                "text": seg_a["text"], "kept_take_start": seg_b["start"]})
    candidates = sorted(silences + fillers + retakes, key=lambda c: c["start"])
    removable = sum((c.get("cut_out", c["end"]) - c.get("cut_in", c["start"])) for c in candidates)
    report = {"source": str(path), "duration": round(total, 3), "noise_db": noise_db,
              "min_duration": min_duration, "silences": silences, "fillers": fillers,
              "retakes": retakes, "candidates": candidates,
              "removable_seconds": round(removable, 3),
              "note": "Candidates only; keep pauses that carry tension or setup (PRODUCTION_RULES.md)."}
    if output:
        write_json(output, report)
    return report


def keep_ranges(candidates: list[dict[str, Any]], total: float) -> list[tuple[float, float]]:
    """The (in, out) ranges that remain after cutting every candidate."""
    ranges, cursor = [], 0.0
    for cut in sorted(candidates, key=lambda c: c.get("cut_in", c["start"])):
        a, b = cut.get("cut_in", cut["start"]), cut.get("cut_out", cut["end"])
        if a > cursor:
            ranges.append((round(cursor, 3), round(a, 3)))
        cursor = max(cursor, b)
    if cursor < total:
        ranges.append((round(cursor, 3), round(total, 3)))
    return ranges


# --- GenerateProxies ----------------------------------------------------------


def generate_proxies(paths: Iterable[str | Path], out_dir: str | Path, *, height: int = 540,
                     crf: int = 23, preset: str = "veryfast", overwrite: bool = False,
                     tonemap_hdr: bool = True) -> dict[str, Any]:
    """Edit-friendly H.264 proxies at `height`, keeping the source frame rate and timecode."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    proxies = []
    for source in paths:
        source = Path(source)
        info = ffprobe_json(source)
        stream = video_stream(info)
        if stream is None:
            raise EditRoomError(f"{source.name} has no video stream to proxy.")
        dest = out_dir / f"{source.stem}_proxy{height}.mp4"
        if dest.exists() and not overwrite:
            proxies.append({"source": str(source), "proxy": str(dest), "skipped": "exists"})
            continue
        filters = [f"scale=-2:{height}:flags=bicubic"]
        hdr = (stream.get("color_transfer") or "").lower() in ("smpte2084", "arib-std-b67")
        if hdr and tonemap_hdr:
            filters = ["zscale=t=linear:npl=100,format=gbrpf32le,zscale=p=bt709,tonemap=hable:desat=0,"
                       "zscale=t=bt709:m=bt709:r=tv", *filters]
        filters.append("format=yuv420p")
        args = ["-i", str(source), "-map", "0:v:0", "-map", "0:a?", "-vf", ",".join(filters),
                "-c:v", "libx264", "-preset", preset, "-crf", str(crf), "-g", "30",
                "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", "-map_metadata", "0",
                str(dest)]
        run_ffmpeg(args)
        proxies.append({"source": str(source), "proxy": str(dest),
                        "source_size": f"{stream.get('width')}x{stream.get('height')}",
                        "hdr_tonemapped": bool(hdr and tonemap_hdr)})
    return {"out_dir": str(out_dir), "height": height, "proxies": proxies,
            "note": "Conform back to the native-resolution sources for the export; never upscale a proxy."}
