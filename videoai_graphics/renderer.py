"""FFmpeg rendering with isolated ASS resources and atomic output publication.

Every render obtains music and sound effects through the Epidemic adapter.
Source audio tracks remain separate and are mixed with those required assets.
"""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from typing import Any


class RenderError(RuntimeError):
    """A source, FFmpeg, or output-publication error."""


def prepare_audio(config: dict[str, Any], duration: float, workspace: Path, *,
                  ffprobe: str) -> dict[str, Any]:
    """Lazy adapter import keeps CLI help and compilation independent of providers."""
    from .epidemic import prepare_audio as provider_prepare_audio

    return provider_prepare_audio(config, duration, workspace, ffprobe=ffprobe)


def _run(command: list[str], *, cwd: Path | None = None,
         timeout: float | None = None) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(command, cwd=cwd, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=timeout,
                              check=False)
    except FileNotFoundError as exc:
        raise RenderError(f"Executable not found: {command[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise RenderError(f"FFmpeg operation exceeded {timeout:g} seconds.") from exc
    except OSError as exc:
        raise RenderError(f"Could not start {command[0]}: {exc}") from exc


def _executable(value: str) -> str:
    """Resolve before switching into the temporary render directory."""
    found = shutil.which(str(value))
    if found:
        return str(Path(found).resolve())
    candidate = Path(value).expanduser()
    if candidate.is_file():
        return str(candidate.resolve())
    raise RenderError(f"Executable not found: {value}")


def _positive_number(value: Any, label: str) -> float:
    try:
        number = float(value)
    except (ValueError, TypeError) as exc:
        raise RenderError(f"{label} must be a positive number.") from exc
    if not math.isfinite(number) or number <= 0:
        raise RenderError(f"{label} must be a positive finite number.")
    return number


def probe_video(input_path: str | Path, *, ffprobe: str = "ffprobe") -> dict[str, Any]:
    source = Path(input_path).expanduser().resolve()
    if not source.is_file():
        raise RenderError(f"Input video does not exist: {source}")
    result = _run([_executable(ffprobe), "-v", "error", "-show_streams", "-show_format",
                   "-of", "json", str(source)],
                  timeout=30)
    if result.returncode:
        raise RenderError(f"FFprobe failed: {result.stderr.strip()[-4000:]}")
    try:
        data = json.loads(result.stdout)
        stream = next(item for item in data["streams"] if item.get("codec_type") == "video")
        width = int(stream["width"])
        height = int(stream["height"])
    except (ValueError, KeyError, IndexError, TypeError, StopIteration) as exc:
        raise RenderError("FFprobe did not return a usable video stream.") from exc
    if width <= 0 or height <= 0:
        raise RenderError("Input video dimensions must be positive.")
    if str(stream.get("color_transfer", "")).lower() in {"smpte2084", "arib-std-b67"}:
        raise RenderError("Input video uses PQ/HLG HDR. Normalize it to SDR before applying "
                          "overlays; this renderer produces 8-bit SDR H.264 output.")
    if stream.get("disposition", {}).get("attached_pic"):
        raise RenderError("The first video stream is an attached picture, not a video timeline.")
    sar = stream.get("sample_aspect_ratio")
    if sar not in (None, "N/A", "0:1", "1:1"):
        raise RenderError("Input video uses non-square pixels. Normalize its pixel aspect "
                          "ratio to 1:1 before applying overlays.")
    rotations = [stream.get("tags", {}).get("rotate", 0)]
    rotations.extend(item.get("rotation", 0) for item in stream.get("side_data_list", []))
    for value in rotations:
        try:
            rotation = float(value)
        except (TypeError, ValueError) as exc:
            raise RenderError("Input video has unreadable rotation metadata.") from exc
        if not math.isfinite(rotation) or abs(rotation % 360) > 0.01:
            raise RenderError("Input video has rotation metadata. Normalize its orientation "
                              "before applying overlays so positions match the picture.")
    raw_duration = stream.get("duration")
    if raw_duration in (None, "N/A"):
        raw_duration = data.get("format", {}).get("duration")
    duration = _positive_number(raw_duration, "Input video duration")
    tags = data.get("format", {}).get("tags", {})
    comment = next((value for key, value in tags.items() if key.lower() == "comment"), "")
    try:
        embedded = json.loads(comment)
        audio_manifest = embedded.get("videoai_audio") if isinstance(embedded, dict) else None
    except (ValueError, TypeError):
        audio_manifest = None
    return {"width": width, "height": height, "duration": duration,
            "frame_rate": stream.get("avg_frame_rate", "0/0"), "input": str(source),
            "audio_count": sum(item.get("codec_type") == "audio" for item in data["streams"]),
            "audio_manifest": audio_manifest}


def _destination(output_path: str | Path, *, source: Path | None,
                 overwrite: bool) -> Path:
    target = Path(output_path).expanduser().resolve()
    if source is not None:
        same = target == source
        if target.exists():
            try:
                same = same or os.path.samefile(source, target)
            except OSError:
                pass
        if same:
            raise RenderError("Output must be a different file from the input video.")
    if target.suffix.lower() not in {".mp4", ".mov", ".mkv"}:
        raise RenderError("Output must use .mp4, .mov, or .mkv.")
    if target.exists() and not overwrite:
        raise RenderError(f"Output already exists; use --overwrite to replace it: {target}")
    if target.exists() and not target.is_file():
        raise RenderError(f"Output is not a regular file: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def _copy_fonts(fonts_dir: str | Path | None, workspace: Path) -> bool:
    if fonts_dir is None:
        return False
    source = Path(fonts_dir).expanduser().resolve()
    if not source.is_dir():
        raise RenderError(f"Fonts directory does not exist: {source}")
    destination = workspace / "fonts"
    destination.mkdir()
    fonts = sorted(path for path in source.rglob("*")
                   if path.is_file() and path.suffix.lower() in {".ttf", ".otf", ".ttc"})
    if not fonts:
        raise RenderError(f"No TTF, OTF, or TTC font files found in: {source}")
    for index, font in enumerate(fonts):
        # libass reads internal font names; safe basenames avoid filter escaping.
        shutil.copyfile(font, destination / f"font_{index:04d}{font.suffix.lower()}")
    return True


def _publish(temporary: Path, target: Path, overwrite: bool) -> None:
    if overwrite:
        os.replace(temporary, target)
    else:
        # Linking a complete file is atomic and fails if another process created
        # the target while encoding. Both paths are on the same filesystem.
        os.link(temporary, target)
        temporary.unlink()


def _safe_audio_manifest(plan: dict[str, Any]) -> dict[str, Any]:
    """Restrict public provenance to asset metadata; never include local paths or URLs."""
    manifest = plan.get("manifest")
    if not isinstance(manifest, dict) or manifest.get("provider") != "epidemic" or manifest.get("api") != "official_mcp":
        raise RenderError("Epidemic audio preparation did not return official API provenance.")

    def fields(value: dict[str, Any], allowed: tuple[str, ...]) -> dict[str, Any]:
        result = {}
        for key in allowed:
            if key not in value:
                continue
            item = value[key]
            if isinstance(item, str):
                result[key] = re.sub(r"https?://\S+", "[URL omitted]", item, flags=re.IGNORECASE)
            elif isinstance(item, (int, float)) and not isinstance(item, bool) and math.isfinite(item):
                result[key] = item
        return result

    asset_fields = ("id", "title", "query", "gain_db", "sha256", "fetched_at")
    result = fields(manifest, ("provider", "api", "fetched_at"))
    # Use the exact selected assets, not unrelated metadata supplied alongside them.
    result["music"] = fields(plan["music"], asset_fields)
    result["sfx"] = [fields(effect, (*asset_fields, "start", "duration")) for effect in plan["sfx"]]
    if not result["music"].get("id") or any(not item.get("id") for item in result["sfx"]):
        raise RenderError("Epidemic music and sound effects must include asset IDs.")
    return result


def _audio_mix(plan: dict[str, Any], duration: float, source_tracks: int) -> tuple[list[str], list[str], int]:
    """Build an independent mix for each source track, or one mix for a silent source."""
    music = plan.get("music")
    effects = plan.get("sfx")
    if not isinstance(music, dict) or not isinstance(effects, list) or not effects:
        raise RenderError("Every render requires Epidemic music and at least one Epidemic sound effect.")
    if any(not isinstance(item, dict) for item in effects):
        raise RenderError("Epidemic returned an invalid sound-effect selection.")

    def local_asset(item: dict[str, Any]) -> str:
        raw = item.get("path")
        if not isinstance(raw, (str, Path)):
            raise RenderError("Epidemic audio preparation did not provide a local asset file.")
        path = Path(raw).expanduser().resolve()
        if not path.is_file():
            raise RenderError("An audio asset prepared by Epidemic is missing.")
        return str(path)

    def number(item: dict[str, Any], key: str, default: float) -> float:
        try:
            value = float(item.get(key, default))
        except (ValueError, TypeError) as exc:
            raise RenderError(f"Epidemic audio {key} must be a finite number.") from exc
        if not math.isfinite(value):
            raise RenderError(f"Epidemic audio {key} must be a finite number.")
        return value

    inputs = ["-stream_loop", "-1", "-i", local_asset(music)]
    length = f"{duration:.6f}"
    audio_format = "aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo"
    fade = min(0.6, duration / 4)
    music_gain = number(music, "gain_db", -24)
    graph = [f"[1:a:0]{audio_format},asetpts=PTS-STARTPTS,atrim=duration={length},"
             f"volume={music_gain:g}dB,afade=t=in:d={fade:.6f},"
             f"afade=t=out:st={duration-fade:.6f}:d={fade:.6f}[musicbed]"]
    for index, effect in enumerate(effects):
        start = number(effect, "start", 0)
        effect_duration = number(effect, "duration", 1)
        if start < 0 or start >= duration or effect_duration <= 0:
            raise RenderError("Epidemic sound-effect timing must fall within the video duration.")
        effect_duration = min(effect_duration, duration - start)
        if effect_duration < 0.02:
            raise RenderError("Each Epidemic sound effect must last at least 0.02 seconds within the video.")
        effect_gain = number(effect, "gain_db", -14)
        inputs += ["-i", local_asset(effect)]
        edge = min(0.03, effect_duration / 4)
        graph.append(f"[{index+2}:a:0]{audio_format},atrim=duration={effect_duration:.6f},"
                     f"asetpts=PTS-STARTPTS,volume={effect_gain:g}dB,"
                     f"afade=t=in:d={edge:.6f},afade=t=out:st={effect_duration-edge:.6f}:d={edge:.6f},"
                     f"adelay=delays={round(start*48000)}S:all=1,apad,atrim=duration={length}[effect{index}]")
    effect_labels = "".join(f"[effect{index}]" for index in range(len(effects)))
    graph.append(f"{effect_labels}amix=inputs={len(effects)}:duration=longest:dropout_transition=0:normalize=0[effectsbed]")
    output_tracks = max(1, source_tracks)
    graph.append(f"[musicbed]asplit={output_tracks}" + "".join(f"[music{index}]" for index in range(output_tracks)))
    graph.append(f"[effectsbed]asplit={output_tracks}" + "".join(f"[effects{index}]" for index in range(output_tracks)))
    for index in range(output_tracks):
        if source_tracks:
            graph.append(f"[0:a:{index}]aresample=48000:async=1:first_pts=0,"
                         f"aformat=sample_fmts=fltp:channel_layouts=stereo,apad,atrim=duration={length},"
                         f"asplit=2[source{index}][sidechain{index}]")
            graph.append(f"[music{index}][sidechain{index}]sidechaincompress=threshold=0.025:ratio=6:"
                         f"attack=20:release=300:makeup=1[ducked{index}]")
            members = f"[source{index}][ducked{index}][effects{index}]"
            count = 3
        else:
            members, count = f"[music{index}][effects{index}]", 2
        graph.append(f"{members}amix=inputs={count}:duration=longest:dropout_transition=0:normalize=0,"
                     f"alimiter=limit=0.95:level=false:latency=true,apad,atrim=duration={length}[aout{index}]")
    return inputs, graph, output_tracks


def _render(compiled: dict[str, Any], target: Path, input_args: list[str], *,
            config: dict[str, Any], source_metadata: bool, encoder: str, fonts_dir: str | Path | None,
            overwrite: bool, ffmpeg: str, ffprobe: str, expected_media: dict[str, Any],
            timeout: float | None) -> dict[str, Any]:
    if encoder not in {"auto", "cpu", "nvenc"}:
        raise RenderError("Encoder must be auto, cpu, or nvenc.")
    executable = _executable(ffmpeg)
    probe_executable = _executable(ffprobe)
    if timeout is None:
        timeout = max(300.0, float(compiled["duration"]) * 30.0)
    else:
        timeout = _positive_number(timeout, "Render timeout")
    fd, name = tempfile.mkstemp(prefix=f".{target.stem}.", suffix=f".partial{target.suffix}",
                                dir=target.parent)
    os.close(fd)
    temporary = Path(name)
    fallback_reason = None
    try:
        with tempfile.TemporaryDirectory(prefix="videoai_graphics_") as folder:
            workspace = Path(folder)
            plan = prepare_audio(config, float(compiled["duration"]), workspace, ffprobe=probe_executable)
            audio_inputs, audio_graph, output_tracks = _audio_mix(plan, float(compiled["duration"]), expected_media["audio_count"])
            audio_manifest = _safe_audio_manifest(plan)
            (workspace / "graphics.ass").write_text(compiled["ass"], encoding="utf-8-sig")
            has_fonts = _copy_fonts(fonts_dir, workspace)
            filter_value = "ass=filename=graphics.ass"
            if has_fonts:
                filter_value += ":fontsdir=fonts"
            graph = ";".join([f"[0:v:0]{filter_value}[vout]", *audio_graph])
            base = [executable, "-hide_banner", "-nostdin", "-xerror", "-loglevel", "warning", "-y",
                    *input_args, *audio_inputs, "-filter_complex", graph, "-map", "[vout]"]
            for index in range(output_tracks):
                base += ["-map", f"[aout{index}]"]
            if source_metadata:
                base += ["-map_metadata", "0", "-map_chapters", "0"]
                for index in range(expected_media["audio_count"]):
                    base += [f"-map_metadata:s:a:{index}", f"0:s:a:{index}"]
            provenance = json.dumps({"videoai_audio": audio_manifest}, ensure_ascii=True, separators=(",", ":"))
            base += ["-metadata", f"comment={provenance}", "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
                     "-pix_fmt", "yuv420p", "-t", f"{float(compiled['duration']):.6f}"]
            if target.suffix.lower() in {".mp4", ".mov"}:
                base += ["-movflags", "+faststart"]
            attempts = ["nvenc", "cpu"] if encoder == "auto" else [encoder]
            used_encoder = attempts[0]
            for attempt in attempts:
                options = (["-c:v", "h264_nvenc", "-preset", "p5", "-cq", "20", "-b:v", "0"]
                           if attempt == "nvenc" else
                           ["-c:v", "libx264", "-preset", "medium", "-crf", "18"])
                result = _run([*base, *options, str(temporary)], cwd=workspace,
                              timeout=timeout)
                if result.returncode == 0:
                    used_encoder = attempt
                    break
                detail = result.stderr.strip()[-6000:] or "FFmpeg returned no error details."
                if attempt == "nvenc" and encoder == "auto":
                    fallback_reason = detail
                    continue
                raise RenderError(f"FFmpeg {attempt} rendering failed: {detail}")
            if not temporary.exists() or temporary.stat().st_size == 0:
                raise RenderError("FFmpeg reported success but produced an empty video.")
            rendered = probe_video(temporary, ffprobe=probe_executable)
            if (rendered["width"], rendered["height"]) != (expected_media["width"], expected_media["height"]):
                raise RenderError("Rendered video dimensions do not match the source.")
            if abs(rendered["duration"] - expected_media["duration"]) > 0.25:
                raise RenderError("Rendered video duration differs from the expected duration by over 0.25 seconds.")
            if rendered["audio_count"] != output_tracks:
                raise RenderError("Rendered video does not preserve the expected number of audio streams.")
            if rendered.get("audio_manifest") != audio_manifest:
                raise RenderError("Rendered video does not contain the required Epidemic asset provenance.")
            try:
                _publish(temporary, target, overwrite)
            except OSError as exc:
                raise RenderError(f"Could not publish the finished video: {exc}") from exc
    finally:
        # Only this invocation's unique temporary output is ever removed.
        temporary.unlink(missing_ok=True)
    return {"output": str(target), "encoder": used_encoder,
            "fallback_reason": fallback_reason, "duration": compiled["duration"],
            "caption_count": compiled["caption_count"], "overlay_count": compiled["overlay_count"],
            "audio_manifest": audio_manifest}


def render_video(config: dict[str, Any], input_path: str | Path, output_path: str | Path, *,
                 encoder: str = "auto", fonts_dir: str | Path | None = None,
                 overwrite: bool = False, ffmpeg: str = "ffmpeg", ffprobe: str = "ffprobe",
                 timeout: float | None = None) -> dict[str, Any]:
    from .compiler import compile_graphics

    source = Path(input_path).expanduser().resolve()
    target = _destination(output_path, source=source, overwrite=overwrite)
    media = probe_video(source, ffprobe=ffprobe)
    if media["width"] % 2 or media["height"] % 2:
        raise RenderError("H.264 output requires even source dimensions. Resize the source first.")
    compiled = compile_graphics(config, media["width"], media["height"], media["duration"])
    result = _render(compiled, target, ["-noautorotate", "-i", str(source)],
                     config=config, source_metadata=True, encoder=encoder, fonts_dir=fonts_dir,
                     overwrite=overwrite, ffmpeg=ffmpeg, ffprobe=ffprobe,
                     expected_media=media, timeout=timeout)
    return {**result, "input": str(source), "width": media["width"], "height": media["height"],
            "audio": ("Each source track mixed separately with Epidemic music and sound effects (stereo AAC)."
                      if media["audio_count"] else "Epidemic music and sound effects (stereo AAC).")}


def render_synthetic(config: dict[str, Any], output_path: str | Path, *,
                     encoder: str = "cpu", fonts_dir: str | Path | None = None,
                     overwrite: bool = False, ffmpeg: str = "ffmpeg", ffprobe: str = "ffprobe",
                     timeout: float | None = None) -> dict[str, Any]:
    from .compiler import compile_graphics

    width = int(config.get("width", 1280))
    height = int(config.get("height", 720))
    if width <= 0 or height <= 0 or width % 2 or height % 2:
        raise RenderError("Demo dimensions must be positive even integers.")
    fps = _positive_number(config.get("fps", 30), "Demo frame rate")
    duration = _positive_number(config.get("duration", 8), "Demo duration")
    target = _destination(output_path, source=None, overwrite=overwrite)
    compiled = compile_graphics(config, width, height, duration)
    color = f"color=c=0x101622:s={width}x{height}:r={fps:g}:d={duration:g}"
    result = _render(compiled, target, ["-f", "lavfi", "-i", color], config=config, source_metadata=False,
                     encoder=encoder, fonts_dir=fonts_dir, overwrite=overwrite,
                     ffmpeg=ffmpeg, ffprobe=ffprobe,
                     expected_media={"width": width, "height": height, "duration": duration, "audio_count": 0},
                     timeout=timeout)
    return {**result, "width": width, "height": height,
            "audio": "Epidemic music and sound effects (stereo AAC)."}
