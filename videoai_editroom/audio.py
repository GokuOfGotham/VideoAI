"""Audio mixer: dialogue clean-up, music ducking, and ADR with the house voice.

``clean_dialogue`` is FFmpeg's spectral denoiser plus a high-pass, de-esser and
gentle compression; it isolates speech from hum, wind and room noise without
a cloud model. ``apply_audio_ducking`` writes explicit gain keyframes from the
dialogue envelope (so the mix is inspectable) and applies them with
``volume`` expressions. ``generate_adr`` re-records a ruined line with the
approved Cedar preset and drops it into the dialogue track at the marked
range; the project policy does not clone voices, and the tool says so instead
of pretending the replacement is the original talent.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import numpy as np

from .common import EditRoomError, audio_streams, decode_mono, ffprobe_json, media_duration, run_ffmpeg, write_json


VIDEO_CONTAINERS = (".mp4", ".mov", ".mkv", ".m4v", ".webm")


def _keep_video(source: Path, output: Path) -> bool:
    """Copy the picture through only when the source has one and the output can hold it."""
    from .common import video_stream
    return output.suffix.lower() in VIDEO_CONTAINERS and video_stream(ffprobe_json(source)) is not None


def _out_args(source: Path, output: Path, *, audio_filter: str) -> list[str]:
    """Filter the first audio stream; copy the video stream when there is one."""
    args = ["-i", str(source), "-af", audio_filter, "-map", "0:a:0"]
    if _keep_video(source, output):
        args += ["-map", "0:v:0", "-c:v", "copy"]
    if output.suffix.lower() == ".wav":
        args += ["-c:a", "pcm_s16le"]
    else:
        args += ["-c:a", "aac", "-b:a", "192k"]
    return args + [str(output)]


def measure_loudness(path: str | Path) -> dict[str, float]:
    """Integrated LUFS, true peak and loudness range from ebur128."""
    log = run_ffmpeg(["-i", str(path), "-map", "0:a:0", "-af", "ebur128=peak=true", "-f", "null", "-"])
    summary = log[log.rfind("Summary:"):] if "Summary:" in log else log
    def grab(label: str) -> float:
        match = re.search(rf"{label}:\s*(-?[0-9.]+|-inf)", summary)
        if not match:
            return float("nan")
        return float("-inf") if match.group(1) == "-inf" else float(match.group(1))
    return {"integrated_lufs": grab("I"), "loudness_range_lu": grab("LRA"), "true_peak_dbtp": grab("Peak")}


# --- CleanDialogue ------------------------------------------------------------


def clean_dialogue(path: str | Path, output: str | Path, *, strength: str = "medium",
                   highpass_hz: int = 80, target_lufs: float | None = -16.0,
                   report: str | Path | None = None) -> dict[str, Any]:
    """Denoise, de-hum, de-ess and level a dialogue recording.

    ``strength`` is light/medium/heavy (afftdn noise floor and reduction). The
    chain never time-stretches or pitch-shifts; the policy forbids both.
    """
    path, output = Path(path), Path(output)
    if not audio_streams(ffprobe_json(path)):
        raise EditRoomError(f"{path.name} has no audio stream.")
    levels = {"light": ("nr=8:nf=-40", "0.4"), "medium": ("nr=14:nf=-32", "0.6"),
              "heavy": ("nr=22:nf=-25", "0.8")}
    if strength not in levels:
        raise EditRoomError("strength must be light, medium or heavy.")
    nr, deess = levels[strength]
    chain = [f"highpass=f={highpass_hz}", "lowpass=f=12000",
             f"afftdn={nr}:tn=1", f"deesser=i={deess}:m=0.5:f=0.5",
             "acompressor=threshold=-18dB:ratio=2.5:attack=12:release=180:makeup=2",
             "alimiter=limit=0.95:level=false"]
    if target_lufs is not None:
        chain.append(f"loudnorm=I={target_lufs}:TP=-1.5:LRA=11")
    before = measure_loudness(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    run_ffmpeg(_out_args(path, output, audio_filter=",".join(chain)))
    after = measure_loudness(output)
    result = {"source": str(path), "output": str(output), "strength": strength, "filters": chain,
              "before": before, "after": after,
              "note": "Listen to sibilants and room tone on a real pass; heavy denoising can hollow speech."}
    if report:
        write_json(report, result)
    return result


# --- ApplyAudioDucking --------------------------------------------------------


def ducking_keyframes(dialogue: str | Path, *, duck_db: float = -14.0, threshold_db: float = -40.0,
                      attack: float = 0.15, release: float = 0.6, hop: float = 0.05,
                      hold: float = 0.25) -> list[dict[str, float]]:
    """Gain keyframes (time, dB) for the music track from where speech is present."""
    rate = 8000
    samples = decode_mono(dialogue, rate)
    step = max(1, int(hop * rate))
    frames = samples.size // step
    if frames == 0:
        return [{"time": 0.0, "gain_db": 0.0}]
    rms = np.sqrt((samples[: frames * step].reshape(frames, step) ** 2).mean(axis=1) + 1e-12)
    speaking = 20 * np.log10(rms) > threshold_db
    # hold: keep the duck through short gaps between words
    hold_frames = int(hold / hop)
    padded = speaking.copy()
    last = -10 ** 9
    for i, flag in enumerate(speaking):
        if flag:
            last = i
        elif i - last <= hold_frames:
            padded[i] = True
    keys: list[dict[str, float]] = [{"time": 0.0, "gain_db": duck_db if padded[0] else 0.0}]
    state = bool(padded[0])
    for i in range(1, frames):
        if bool(padded[i]) != state:
            state = bool(padded[i])
            t = i * hop
            if state:
                keys.append({"time": round(max(0.0, t - attack), 3), "gain_db": 0.0})
                keys.append({"time": round(t, 3), "gain_db": duck_db})
            else:
                keys.append({"time": round(t, 3), "gain_db": duck_db})
                keys.append({"time": round(t + release, 3), "gain_db": 0.0})
    return keys


def _volume_expression(keys: list[dict[str, float]]) -> str:
    """Piecewise-linear FFmpeg `volume` expression (linear gain from dB keyframes)."""
    if len(keys) == 1:
        return f"pow(10,{keys[0]['gain_db']}/20)"
    expr = f"{keys[-1]['gain_db']}"
    for a, b in reversed(list(zip(keys, keys[1:]))):
        t0, t1, g0, g1 = a["time"], b["time"], a["gain_db"], b["gain_db"]
        if t1 - t0 <= 0:
            segment = f"{g1}"
        else:
            segment = f"({g0}+({g1}-{g0})*(t-{t0})/({t1 - t0}))"
        expr = f"if(lt(t,{t1}),{segment},{expr})"
    expr = f"if(lt(t,{keys[0]['time']}),{keys[0]['gain_db']},{expr})"
    return f"pow(10,({expr})/20)"


def apply_audio_ducking(music: str | Path, dialogue: str | Path, output: str | Path, *,
                        duck_db: float = -14.0, music_gain_db: float = -6.0, threshold_db: float = -40.0,
                        attack: float = 0.15, release: float = 0.6, mix: bool = True,
                        keyframes_out: str | Path | None = None) -> dict[str, Any]:
    """Ducks `music` under `dialogue` with explicit keyframes; optionally mixes them.

    With ``mix`` the output carries the dialogue plus ducked music; without it
    the output is the ducked music alone for a separate stem. Dialogue is not
    processed here; run ``clean_dialogue`` first when it needs it.
    """
    music, dialogue, output = Path(music), Path(dialogue), Path(output)
    keys = ducking_keyframes(dialogue, duck_db=duck_db, threshold_db=threshold_db, attack=attack, release=release)
    expr = _volume_expression(keys).replace(",", "\\,")
    duration = media_duration(dialogue)
    music_chain = (f"[1:a:0]aloop=loop=-1:size=2e9,atrim=0:{duration:.3f},asetpts=PTS-STARTPTS,"
                   f"volume={music_gain_db}dB,volume='{expr}':eval=frame[mus]")
    if mix:
        graph = (f"[0:a:0]aresample=48000,aformat=channel_layouts=stereo[dia];{music_chain};"
                 f"[dia][mus]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.95:level=false[aout]")
    else:
        graph = f"{music_chain};[mus]aformat=channel_layouts=stereo[aout]"
    output.parent.mkdir(parents=True, exist_ok=True)
    args = ["-i", str(dialogue), "-stream_loop", "-1", "-i", str(music), "-filter_complex", graph,
            "-map", "[aout]", "-t", f"{duration:.3f}"]
    if _keep_video(dialogue, output):
        args += ["-map", "0:v:0", "-c:v", "copy"]
    args += (["-c:a", "pcm_s16le"] if output.suffix.lower() == ".wav" else ["-c:a", "aac", "-b:a", "192k"])
    run_ffmpeg(args + [str(output)])
    ducked = sum(1 for k in keys if k["gain_db"] == duck_db) // 2
    result = {"dialogue": str(dialogue), "music": str(music), "output": str(output), "duck_db": duck_db,
              "music_gain_db": music_gain_db, "speech_regions": ducked, "keyframes": keys,
              "loudness": measure_loudness(output),
              "note": "Confirm dialogue stays centred and intelligible on a mono fold-down."}
    if keyframes_out:
        write_json(keyframes_out, {"keyframes": keys, "expression": expr})
    return result


# --- GenerateADR --------------------------------------------------------------


def generate_adr(track: str | Path, output: str | Path, *, text: str, start: float, end: float,
                 room_tone_from: tuple[float, float] | None = None, crossfade: float = 0.04,
                 preset: dict[str, Any] | None = None, work_dir: str | Path | None = None) -> dict[str, Any]:
    """Replaces the dialogue between `start` and `end` with a new Cedar take of `text`.

    The take is synthesised with the approved preset, never stretched: if it
    runs longer than the gap the tool reports the overrun and asks for a
    rewrite instead of squeezing it (AGENTS.md). Room tone from a quiet part
    of the track (or the gap itself) fills any remaining space so the splice
    does not go dead.
    """
    from narration_tools import synthesize
    track, output = Path(track), Path(output)
    if end <= start:
        raise EditRoomError("end must be after start.")
    total = media_duration(track)
    if end > total + 0.01:
        raise EditRoomError(f"The range ends after the track ({total:.2f}s).")
    work = Path(work_dir) if work_dir else output.parent / "_adr_work"
    work.mkdir(parents=True, exist_ok=True)
    take = synthesize(text, work / "adr_take.wav", preset)
    take_length = media_duration(take)
    gap = end - start
    if take_length > gap + 0.05:
        return {"status": "rewrite_needed", "text": text, "take": str(take), "take_seconds": round(take_length, 3),
                "gap_seconds": round(gap, 3), "overrun_seconds": round(take_length - gap, 3),
                "note": "The new line is longer than the hole. Shorten the line or widen the range; "
                        "the take is not time-stretched."}
    tone_in, tone_out = room_tone_from or (start, min(start + 0.4, end))
    output.parent.mkdir(parents=True, exist_ok=True)
    graph = (f"[0:a:0]atrim=0:{start:.3f},asetpts=PTS-STARTPTS[head];"
             f"[0:a:0]atrim={end:.3f},asetpts=PTS-STARTPTS[tail];"
             f"[0:a:0]atrim={tone_in:.3f}:{tone_out:.3f},asetpts=PTS-STARTPTS,aloop=loop=-1:size=2e9,"
             f"atrim=0:{gap:.3f},asetpts=PTS-STARTPTS,volume=0.9[tone];"
             f"[1:a:0]aresample=48000,apad,atrim=0:{gap:.3f},asetpts=PTS-STARTPTS[take];"
             f"[tone][take]amix=inputs=2:duration=first:normalize=0[fill];"
             f"[head][fill]acrossfade=d={crossfade}:c1=tri:c2=tri[hf];"
             f"[hf][tail]acrossfade=d={crossfade}:c1=tri:c2=tri,aformat=sample_rates=48000:channel_layouts=stereo[aout]")
    args = ["-i", str(track), "-i", str(take), "-filter_complex", graph, "-map", "[aout]"]
    if _keep_video(track, output):
        args += ["-map", "0:v:0", "-c:v", "copy"]
    args += (["-c:a", "pcm_s16le"] if output.suffix.lower() == ".wav" else ["-c:a", "aac", "-b:a", "192k"])
    run_ffmpeg(args + [str(output)])
    return {"status": "replaced", "track": str(track), "output": str(output), "text": text,
            "range": [start, end], "take": str(take), "take_seconds": round(take_length, 3),
            "slack_seconds": round(gap - take_length, 3), "voice": "approved Cedar preset",
            "note": "This is the house narration voice, not a clone of the original speaker; "
                    "label it as re-voiced where the policy requires attribution."}
