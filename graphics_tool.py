"""Compile VideoAI graphics; every video render requires Epidemic music and SFX."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Any


PRESETS = ("political", "space", "gaming", "reaction")


def demo_config(preset: str, width: int = 1280, height: int = 720) -> dict[str, Any]:
    labels = {"political": ("CONTEXT & COMMENTARY", "A closer look", "Commentary"),
              "space": ("MISSION DESK", "Beyond the frame", "Exploration"),
              "gaming": ("PLAYER VIEW", "Next level", "Gameplay"),
              "reaction": ("FIRST IMPRESSIONS", "Let's break it down", "Reaction")}
    label, title, subtitle = labels[preset]
    phrases = [(0.5, 3.0, "A clearer view of every story"),
               (5.5, 7.8, "Keep the key moment in focus")]
    words = []
    for start, end, sentence in phrases:
        tokens = sentence.split()
        step = (end - start) / len(tokens)
        words.extend({"word": token, "start": round(start + index * step, 3),
                      "end": round(start + (index + 1) * step, 3)}
                     for index, token in enumerate(tokens))
    return {"preset": preset, "width": width, "height": height, "fps": 30, "duration": 8,
            "words": words, "captions": {}, "audio": {"provider": "epidemic"},
            "overlays": [
                {"type": "lower_third", "start": 0, "end": 3, "title": label,
                 "subtitle": "VIDEOAI GRAPHICS DEMO"},
                {"type": "title_card", "start": 3.2, "end": 5.2, "title": title,
                 "subtitle": "Animated titles · Word highlights · Clear captions"},
                {"type": "callout", "start": 5.5, "end": 8, "title": "THE KEY MOMENT",
                 "subtitle": subtitle},
                {"type": "progress_bar", "start": 0, "end": 8, "title": ""}]}


def _config(path: str) -> dict[str, Any]:
    content = json.loads(Path(path).expanduser().read_text(encoding="utf-8-sig"))
    if not isinstance(content, dict):
        raise ValueError("Config JSON must contain an object.")
    return content


def _same_file(first: Path, second: Path) -> bool:
    if first == second:
        return True
    try:
        return first.samefile(second)
    except (FileNotFoundError, OSError):
        return False


def _preflight_outputs(paths: list[str | Path], *, protected: list[str | Path] | None = None,
                       overwrite: bool = False) -> list[Path]:
    """Check the entire output set before any destination directories or files change."""
    targets = [Path(path).expanduser().resolve() for path in paths]
    inputs = [Path(path).expanduser().resolve() for path in (protected or [])]
    for index, target in enumerate(targets):
        if any(_same_file(target, source) for source in inputs):
            raise ValueError(f"Output would overwrite an input file: {target}")
        for other in targets[:index]:
            if _same_file(target, other):
                raise ValueError(f"Duplicate output files: {other} and {target}")
            if target in other.parents or other in target.parents:
                raise ValueError(f"An output file cannot also be an output directory: {other} and {target}")
        if target.exists():
            if not target.is_file():
                raise ValueError(f"Output is not a regular file: {target}")
            if not overwrite:
                raise ValueError(f"Output already exists; use --overwrite to replace it: {target}")
        for ancestor in target.parents:
            if ancestor.exists():
                if not ancestor.is_dir():
                    raise ValueError(f"Output parent is not a directory: {ancestor}")
                break
    return targets


def _write_text(path: str | Path, content: str, *, protected: list[Path] | None = None,
                overwrite: bool = False) -> str:
    target = _preflight_outputs([path], protected=protected, overwrite=overwrite)[0]
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as output:
            output.write(content)
        if overwrite:
            os.replace(temporary, target)
        else:
            os.link(temporary, target)
            temporary.unlink()
    finally:
        temporary.unlink(missing_ok=True)
    return str(target)


def _render_options(parser: argparse.ArgumentParser, *, source: bool) -> None:
    parser.add_argument("--encoder", choices=("auto", "cpu", "nvenc"),
                        default="auto" if source else "cpu")
    parser.add_argument("--fonts-dir", help="Folder of TTF/OTF/TTC fonts for libass.")
    parser.add_argument("--overwrite", action="store_true", help="Replace existing output files.")
    parser.add_argument("--ffmpeg", default="ffmpeg", help="FFmpeg executable name or path.")
    parser.add_argument("--ffprobe", default="ffprobe", help="FFprobe executable name or path.")
    parser.add_argument("--timeout", type=float,
                        help="Encoding timeout in seconds; default scales with video duration.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    compile_parser = commands.add_parser("compile", help="Write ASS overlays/captions and optional SRT.")
    compile_parser.add_argument("--config", required=True)
    compile_parser.add_argument("--output", required=True, help="Destination .ass file.")
    compile_parser.add_argument("--srt", help="Optional plain subtitle sidecar.")
    compile_parser.add_argument("--width", type=int)
    compile_parser.add_argument("--height", type=int)
    compile_parser.add_argument("--overwrite", action="store_true", help="Replace existing ASS/SRT outputs.")
    render_parser = commands.add_parser("render", help="Render graphics and mix required Epidemic music/SFX with source audio.")
    render_parser.add_argument("--config", required=True)
    render_parser.add_argument("--input", required=True)
    render_parser.add_argument("--output", required=True)
    _render_options(render_parser, source=True)
    demo_parser = commands.add_parser("demo", help="Create an eight-second demo config and subtitle files.")
    demo_parser.add_argument("--preset", choices=PRESETS, default="gaming")
    demo_parser.add_argument("--output-dir", required=True)
    demo_parser.add_argument("--width", type=int, default=1280)
    demo_parser.add_argument("--height", type=int, default=720)
    demo_parser.add_argument("--render", action="store_true", help="Also render an MP4 with required live Epidemic music and SFX.")
    _render_options(demo_parser, source=False)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "compile":
            from videoai_graphics.compiler import compile_graphics

            config = _config(args.config)
            width = args.width if args.width is not None else config.get("width", 1920)
            height = args.height if args.height is not None else config.get("height", 1080)
            compiled = compile_graphics(config, width, height, config.get("duration"))
            protected = [Path(args.config).expanduser().resolve()]
            paths = [args.output, *([args.srt] if args.srt else [])]
            targets = _preflight_outputs(paths, protected=protected, overwrite=args.overwrite)
            ass_path = targets[0]
            output = {"ass": _write_text(ass_path, compiled["ass"], protected=protected,
                                         overwrite=args.overwrite)}
            if args.srt:
                output["srt"] = _write_text(targets[1], compiled["srt"], protected=[*protected, ass_path],
                                            overwrite=args.overwrite)
            output.update({key: compiled[key] for key in ("duration", "overlay_count", "caption_count")})
        elif args.command == "render":
            from videoai_graphics.renderer import render_video

            _preflight_outputs([args.output], protected=[args.config, args.input], overwrite=args.overwrite)
            output = render_video(_config(args.config), args.input, args.output,
                                  encoder=args.encoder, fonts_dir=args.fonts_dir,
                                  overwrite=args.overwrite, ffmpeg=args.ffmpeg,
                                  ffprobe=args.ffprobe, timeout=args.timeout)
        else:
            from videoai_graphics.compiler import compile_graphics

            directory = Path(args.output_dir).expanduser().resolve()
            config = demo_config(args.preset, args.width, args.height)
            compiled = compile_graphics(config, args.width, args.height, config["duration"])
            stem = f"{args.preset}_demo"
            paths = [directory / f"{stem}.{extension}" for extension in ("json", "ass", "srt")]
            if args.render:
                paths.append(directory / f"{stem}.mp4")
            targets = _preflight_outputs(paths, overwrite=args.overwrite)
            output = {"config": _write_text(targets[0], json.dumps(config, indent=2) + "\n", overwrite=args.overwrite),
                      "ass": _write_text(targets[1], compiled["ass"], overwrite=args.overwrite),
                      "srt": _write_text(targets[2], compiled["srt"], overwrite=args.overwrite)}
            if args.render:
                from videoai_graphics.renderer import render_synthetic

                output["render"] = render_synthetic(config, targets[3],
                                                    encoder=args.encoder, fonts_dir=args.fonts_dir,
                                                    overwrite=args.overwrite, ffmpeg=args.ffmpeg,
                                                    ffprobe=args.ffprobe, timeout=args.timeout)
        rendered = output.get("render", output)
        if rendered.get("fallback_reason"):
            print("NVENC failed; completed using CPU. Reason: " + rendered["fallback_reason"],
                  file=sys.stderr)
        print(json.dumps(output, indent=2, ensure_ascii=False))
        return 0
    except (ValueError, OSError, RuntimeError, KeyError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
