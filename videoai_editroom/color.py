"""Colorist: shot matching, LUT application, and the built-in transforms.

``match_color`` measures the reference and target shots in CIELAB (sampled
frames, robust mean/std per channel), builds a 3D LUT that moves the target's
statistics onto the reference's, and applies it with FFmpeg's ``lut3d``. The
LUT is written as a .cube file so the grade is inspectable and reusable in
Resolve. ``apply_lut`` takes any .cube LUT or one of the built-in looks; the
log-to-Rec.709 transforms use FFmpeg's colour-managed ``zscale``/``tonemap``
path rather than a guessed curve.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from .common import EditRoomError, audio_streams, ffprobe_json, run_ffmpeg, video_stream, write_json

BUILTIN_LOOKS = {
    "rec709": "identity; useful to confirm the pipeline",
    "hlg_to_rec709": "HLG (BT.2100) to Rec.709 with hable tone mapping",
    "pq_to_rec709": "PQ/HDR10 (SMPTE 2084) to Rec.709 with hable tone mapping",
    "slog3_to_rec709": "Sony S-Log3/S-Gamut3.Cine approximation to Rec.709",
    "clog3_to_rec709": "Canon Log 3 approximation to Rec.709",
    "vlog_to_rec709": "Panasonic V-Log approximation to Rec.709",
    "teal_orange": "gentle cinematic split-tone, shadows cool, skin warm",
    "filmic_contrast": "soft S-curve with protected highlights",
    "news_neutral": "neutral broadcast: slight saturation lift, clean blacks (no lifted blacks)",
}

_HDR_TRANSFER = {"hlg_to_rec709": "arib-std-b67", "pq_to_rec709": "smpte2084"}


# --- Sampling -----------------------------------------------------------------


def _sample_frames(path: Path, count: int, *, size: int = 256) -> np.ndarray:
    import cv2
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        raise EditRoomError(f"OpenCV could not open {path.name}.")
    total = int(capture.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
    picks = np.linspace(0, max(0, total - 1), num=min(count, total), dtype=int)
    frames = []
    for index in picks:
        capture.set(cv2.CAP_PROP_POS_FRAMES, int(index))
        ok, frame = capture.read()
        if ok and frame is not None:
            frames.append(cv2.resize(frame, (size, size), interpolation=cv2.INTER_AREA))
    capture.release()
    if not frames:
        raise EditRoomError(f"No frames could be read from {path.name}.")
    return np.stack(frames)


def _lab_stats(frames_bgr: np.ndarray) -> dict[str, np.ndarray]:
    import cv2
    lab = np.concatenate([cv2.cvtColor(f, cv2.COLOR_BGR2LAB).reshape(-1, 3) for f in frames_bgr]).astype(np.float32)
    lo, hi = np.percentile(lab, [1, 99], axis=0)
    mask = np.all((lab >= lo) & (lab <= hi), axis=1)
    trimmed = lab[mask] if mask.sum() > 100 else lab
    return {"mean": trimmed.mean(axis=0), "std": trimmed.std(axis=0) + 1e-3,
            "black": np.percentile(lab[:, 0], 0.5), "white": np.percentile(lab[:, 0], 99.5)}


# --- LUT construction ---------------------------------------------------------


def _grid(size: int) -> np.ndarray:
    axis = np.linspace(0.0, 1.0, size, dtype=np.float32)
    b, g, r = np.meshgrid(axis, axis, axis, indexing="ij")
    return np.stack([r.ravel(), g.ravel(), b.ravel()], axis=1)  # .cube order: R fastest


def write_cube(path: str | Path, rgb: np.ndarray, size: int, title: str) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    rgb = np.clip(rgb, 0.0, 1.0)
    lines = [f'TITLE "{title}"', f"LUT_3D_SIZE {size}", "DOMAIN_MIN 0.0 0.0 0.0", "DOMAIN_MAX 1.0 1.0 1.0"]
    lines += [f"{r:.6f} {g:.6f} {b:.6f}" for r, g, b in rgb]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def match_lut(reference_stats: dict[str, np.ndarray], target_stats: dict[str, np.ndarray], *, size: int = 33,
              strength: float = 1.0) -> np.ndarray:
    """Reinhard-style statistics transfer in LAB, sampled onto an RGB cube."""
    import cv2
    grid = _grid(size)
    bgr = (grid[:, ::-1] * 255).reshape(-1, 1, 3).astype(np.uint8)
    lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB).reshape(-1, 3).astype(np.float32)
    ratio = np.clip(reference_stats["std"] / target_stats["std"], 0.5, 2.0)
    matched = (lab - target_stats["mean"]) * ratio + reference_stats["mean"]
    matched = lab + (matched - lab) * strength
    matched[:, 0] = np.clip(matched[:, 0], 0, 255)
    matched[:, 1:] = np.clip(matched[:, 1:], 0, 255)
    out_bgr = cv2.cvtColor(matched.reshape(-1, 1, 3).astype(np.uint8), cv2.COLOR_LAB2BGR).reshape(-1, 3)
    return out_bgr[:, ::-1].astype(np.float32) / 255.0


def look_lut(name: str, *, size: int = 33) -> np.ndarray:
    """RGB cube for the creative built-in looks (the log/HDR transforms use filters instead)."""
    grid = _grid(size)
    r, g, b = grid[:, 0], grid[:, 1], grid[:, 2]
    if name == "rec709":
        return grid
    if name == "teal_orange":
        luma = 0.2126 * r + 0.7152 * g + 0.0722 * b
        shadow = np.clip(1.0 - luma * 1.6, 0, 1)[:, None]
        light = np.clip(luma * 1.3 - 0.3, 0, 1)[:, None]
        cool = np.array([-0.04, 0.01, 0.06], dtype=np.float32)
        warm = np.array([0.05, 0.01, -0.05], dtype=np.float32)
        return grid + shadow * cool + light * warm
    if name == "filmic_contrast":
        x = grid
        curve = x * x * (3 - 2 * x)  # smoothstep S-curve
        return x + (curve - x) * 0.55
    if name == "news_neutral":
        luma = (0.2126 * r + 0.7152 * g + 0.0722 * b)[:, None]
        sat = grid + (grid - luma) * 0.12
        return np.clip((sat - 0.01) / 0.99, 0, 1)
    if name in ("slog3_to_rec709", "clog3_to_rec709", "vlog_to_rec709"):
        # Published log curves to scene-linear, then a Rec.709 OETF with a
        # soft shoulder. Camera-matrix (gamut) conversion is left to a
        # manufacturer LUT; this gets the tonality right for an offline pass.
        def slog3(v):
            return np.where(v >= 171.2102946929 / 1023,
                            (10 ** ((v * 1023 - 420) / 261.5)) * (0.18 + 0.01) - 0.01,
                            (v * 1023 - 95) * 0.01125000 / (171.2102946929 - 95))
        def clog3(v):
            return np.where(v < 0.097465473,
                            -(10 ** ((0.12783901 - v) / 0.36726845) - 1) / 14.98325,
                            np.where(v <= 0.15277891, (v - 0.12512219) / 1.9754798,
                                     (10 ** ((v - 0.12240537) / 0.36726845) - 1) / 14.98325))
        def vlog(v):
            return np.where(v < 0.181, (v - 0.125) / 5.6,
                            10 ** ((v - 0.598206) / 0.241514) - 0.00873)
        linear = {"slog3_to_rec709": slog3, "clog3_to_rec709": clog3, "vlog_to_rec709": vlog}[name](grid)
        linear = np.clip(linear / 0.18 * 0.20, 0, None)  # 18% grey -> 20% linear (~0.42 display)
        shoulder = linear / (1 + linear * 0.35)
        out = np.where(shoulder < 0.018, shoulder * 4.5, 1.099 * np.power(np.clip(shoulder, 1e-6, None), 0.45) - 0.099)
        return np.clip(out, 0, 1)
    raise EditRoomError(f"Unknown look '{name}'; choose from {', '.join(BUILTIN_LOOKS)}.")


# --- Tools --------------------------------------------------------------------


def _encode_args(source: Path, output: Path, video_filter: str, *, encoder: str, crf: int) -> list[str]:
    args = ["-i", str(source), "-map", "0:v:0", "-vf", video_filter, "-c:v", encoder]
    if encoder == "libx264":
        args += ["-preset", "medium", "-crf", str(crf)]
    elif encoder.endswith("nvenc"):
        args += ["-preset", "p5", "-cq", str(crf), "-b:v", "0"]
    if audio_streams(ffprobe_json(source)):
        args += ["-map", "0:a", "-c:a", "copy"]
    return args + ["-movflags", "+faststart", str(output)]


def _lut_filter(cube: Path) -> str:
    return f"lut3d=file='{cube.as_posix().replace(':', chr(92) + ':')}':interp=tetrahedral"


def apply_lut(path: str | Path, output: str | Path, *, lut: str | Path, encoder: str = "libx264",
              crf: int = 18, size: int = 33, work_dir: str | Path | None = None) -> dict[str, Any]:
    """Applies a .cube LUT or a built-in look/transform to the whole clip."""
    path, output = Path(path), Path(output)
    if video_stream(ffprobe_json(path)) is None:
        raise EditRoomError(f"{path.name} has no video stream.")
    output.parent.mkdir(parents=True, exist_ok=True)
    lut_name = str(lut)
    if lut_name in _HDR_TRANSFER:
        filters = (f"zscale=t=linear:npl=100,format=gbrpf32le,zscale=p=bt709,tonemap=hable:desat=0,"
                   f"zscale=t=bt709:m=bt709:r=tv,format=yuv420p")
        cube = None
    else:
        if lut_name in BUILTIN_LOOKS:
            work = Path(work_dir) if work_dir else output.parent
            cube = write_cube(work / f"{lut_name}_{size}.cube", look_lut(lut_name, size=size), size, lut_name)
        else:
            cube = Path(lut)
            if not cube.exists():
                raise EditRoomError(f"LUT not found: {cube}")
        filters = f"{_lut_filter(cube)},format=yuv420p"
    run_ffmpeg(_encode_args(path, output, filters, encoder=encoder, crf=crf))
    return {"source": str(path), "output": str(output), "lut": lut_name, "cube": str(cube) if cube else None,
            "filters": filters, "description": BUILTIN_LOOKS.get(lut_name, "user LUT"),
            "note": "Check skin tones and blacks on a full-resolution frame; do not lift blacks or add haze."}


def match_color(reference: str | Path, target: str | Path, output: str | Path, *, strength: float = 1.0,
                samples: int = 24, size: int = 33, encoder: str = "libx264", crf: int = 18,
                cube_out: str | Path | None = None, report: str | Path | None = None) -> dict[str, Any]:
    """Grades `target` so its colour statistics match `reference`, writing the LUT used."""
    reference, target, output = Path(reference), Path(target), Path(output)
    ref_stats = _lab_stats(_sample_frames(reference, samples))
    tgt_stats = _lab_stats(_sample_frames(target, samples))
    if not 0.0 < strength <= 1.0:
        raise EditRoomError("strength must be between 0 and 1.")
    rgb = match_lut(ref_stats, tgt_stats, size=size, strength=strength)
    cube = write_cube(cube_out or output.with_suffix(".match.cube"), rgb, size,
                      f"match {target.stem} to {reference.stem}")
    output.parent.mkdir(parents=True, exist_ok=True)
    run_ffmpeg(_encode_args(target, output, f"{_lut_filter(cube)},format=yuv420p", encoder=encoder, crf=crf))
    after_stats = _lab_stats(_sample_frames(output, samples))
    def rounded(stats):
        return {"mean_lab": [round(float(v), 2) for v in stats["mean"]],
                "std_lab": [round(float(v), 2) for v in stats["std"]],
                "black_l": round(float(stats["black"]), 2), "white_l": round(float(stats["white"]), 2)}
    delta_before = float(np.abs(ref_stats["mean"] - tgt_stats["mean"]).sum())
    delta_after = float(np.abs(ref_stats["mean"] - after_stats["mean"]).sum())
    result = {"reference": str(reference), "target": str(target), "output": str(output), "cube": str(cube),
              "strength": strength, "reference_stats": rounded(ref_stats), "target_stats": rounded(tgt_stats),
              "output_stats": rounded(after_stats), "mean_distance_before": round(delta_before, 2),
              "mean_distance_after": round(delta_after, 2),
              "note": "Statistical match; confirm continuity on adjacent frames of the two shots by eye."}
    if report:
        write_json(report, result)
    return result
