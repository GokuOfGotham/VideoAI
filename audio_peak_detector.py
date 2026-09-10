"""
Audio Peak Detector for VideoAI (Fast Pass Detection Policy).

Extracts audio track from massive raw video files (10GB+) without decoding video,
computes Root-Mean-Square (RMS) energy profiles using fast vectorized NumPy,
and detects and clusters peak audio events (gunfire, explosions, impact hits).
"""

import os
import subprocess
import wave
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np


def extract_audio_track(
    video_path: str,
    output_wav_path: str,
    sample_rate: int = 16000,
    ffmpeg_binary: str = "ffmpeg"
) -> str:
    """
    Rapidly demuxes and decodes the audio track of a video to mono 16-bit PCM WAV.
    Bypasses video frame decoding, running in seconds even on 10GB+ raw footage.
    """
    if not os.path.isfile(video_path):
        raise FileNotFoundError(f"Video file not found: {video_path}")

    os.makedirs(os.path.dirname(os.path.abspath(output_wav_path)), exist_ok=True)

    cmd = [
        ffmpeg_binary,
        "-y",
        "-i", video_path,
        "-vn",                   # Disable video decoding completely
        "-ac", "1",              # Downmix to mono channel
        "-ar", str(sample_rate), # Target sample rate (16kHz standard for analysis)
        "-c:a", "pcm_s16le",     # Uncompressed standard 16-bit linear PCM
        output_wav_path
    ]

    print(f"[*] Demuxing audio track from: {Path(video_path).name} -> {Path(output_wav_path).name}...")
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if res.returncode != 0:
        err = res.stderr[-500:] if res.stderr else "Unknown FFmpeg error"
        raise RuntimeError(f"FFmpeg audio extraction failed (code {res.returncode}):\n{err}")

    if not os.path.isfile(output_wav_path) or os.path.getsize(output_wav_path) == 0:
        raise RuntimeError(f"Extracted audio file is missing or empty: {output_wav_path}")

    size_mb = os.path.getsize(output_wav_path) / (1024 * 1024)
    print(f"[+] Audio extracted successfully ({size_mb:.2f} MB).")
    return output_wav_path


def load_wav_samples(wav_path: str) -> Tuple[np.ndarray, int]:
    """
    Loads raw 16-bit PCM WAV into a normalized float32 NumPy array [-1.0, 1.0].
    Uses standard library wave module for guaranteed zero-dependency stability.
    """
    # Try scipy.io.wavfile if available, otherwise use standard wave
    try:
        from scipy.io import wavfile
        sr, samples = wavfile.read(wav_path)
        if samples.ndim > 1:
            samples = samples.mean(axis=1)
        if samples.dtype == np.int16:
            samples = samples.astype(np.float32) / 32768.0
        elif samples.dtype != np.float32:
            samples = samples.astype(np.float32)
        return samples, sr
    except (ImportError, Exception):
        pass

    with wave.open(wav_path, "rb") as wf:
        n_channels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        framerate = wf.getframerate()
        n_frames = wf.getnframes()
        raw_bytes = wf.readframes(n_frames)

    if sampwidth == 2:
        samples = np.frombuffer(raw_bytes, dtype=np.int16).astype(np.float32) / 32768.0
    elif sampwidth == 4:
        samples = np.frombuffer(raw_bytes, dtype=np.int32).astype(np.float32) / 2147483648.0
    else:
        samples = np.frombuffer(raw_bytes, dtype=np.uint8).astype(np.float32) / 128.0 - 1.0

    if n_channels > 1:
        samples = samples.reshape(-1, n_channels).mean(axis=1)

    return samples, framerate


def compute_sliding_rms(
    samples: np.ndarray,
    sample_rate: int,
    window_sec: float = 0.25,
    hop_sec: float = 0.10
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Computes RMS energy across sliding windows via 1D cumulative summation.
    Executes in milliseconds even for hours of audio with O(N) complexity.
    Returns (timestamps_sec, rms_values).
    """
    if len(samples) == 0:
        return np.array([]), np.array([])

    win_len = max(1, int(round(sample_rate * window_sec)))
    hop_len = max(1, int(round(sample_rate * hop_sec)))

    # Cumulative sum of squared amplitudes
    sq = samples.astype(np.float64) ** 2
    cumsum = np.pad(np.cumsum(sq), (1, 0), mode="constant")

    n_samples = len(samples)
    if n_samples < win_len:
        rms_val = np.sqrt(np.mean(sq))
        return np.array([0.0]), np.array([rms_val])

    indices = np.arange(0, n_samples - win_len + 1, hop_len)
    win_sums = cumsum[indices + win_len] - cumsum[indices]
    rms = np.sqrt(np.maximum(0.0, win_sums / win_len)).astype(np.float32)
    timestamps = (indices + (win_len // 2)) / float(sample_rate)

    return timestamps, rms


def detect_audio_spikes(
    timestamps: np.ndarray,
    rms: np.ndarray,
    min_db: float = -26.0,
    peak_factor: float = 2.2,
    rolling_window_sec: float = 12.0
) -> List[Tuple[float, float]]:
    """
    Identifies sudden volume peaks that exceed the local rolling background energy
    and meet minimum absolute loudness.
    Returns list of (timestamp_sec, peak_rms).
    """
    if len(rms) < 3:
        return []

    # Filter out near-silence using decibels relative to full scale (dBFS)
    min_rms = 10.0 ** (min_db / 20.0)

    # Estimate local rolling baseline energy
    step_sec = timestamps[1] - timestamps[0] if len(timestamps) > 1 else 0.1
    half_win = max(1, int(round((rolling_window_sec / 2.0) / step_sec)))

    cum_rms = np.pad(np.cumsum(rms.astype(np.float64)), (1, 0), mode="constant")
    n = len(rms)
    start_idx = np.maximum(0, np.arange(n) - half_win)
    end_idx = np.minimum(n, np.arange(n) + half_win + 1)
    counts = end_idx - start_idx
    local_mean = (cum_rms[end_idx] - cum_rms[start_idx]) / counts

    # Candidate peaks: local maximum and significant spike above local baseline
    is_local_max = (rms[1:-1] >= rms[:-2]) & (rms[1:-1] >= rms[2:])
    is_spike = (rms[1:-1] >= local_mean[1:-1] * peak_factor) & (rms[1:-1] >= min_rms)

    peak_mask = np.zeros(len(rms), dtype=bool)
    peak_mask[1:-1] = is_local_max & is_spike

    peak_indices = np.where(peak_mask)[0]
    peaks = [(float(timestamps[i]), float(rms[i])) for i in peak_indices]
    return peaks


def cluster_timestamps(
    peaks: List[Tuple[float, float]],
    min_cluster_gap: float = 15.0
) -> List[float]:
    """
    Clusters timestamps occurring within a close time window into a single
    representative peak timestamp with maximum intensity.
    Prevents redundant candidate clips during sustained firefights.
    """
    if not peaks:
        return []

    sorted_peaks = sorted(peaks, key=lambda x: x[0])
    clusters: List[List[Tuple[float, float]]] = []
    current_cluster = [sorted_peaks[0]]

    for p in sorted_peaks[1:]:
        last_t = current_cluster[-1][0]
        if (p[0] - last_t) <= min_cluster_gap:
            current_cluster.append(p)
        else:
            clusters.append(current_cluster)
            current_cluster = [p]

    if current_cluster:
        clusters.append(current_cluster)

    clustered_timestamps = []
    for c in clusters:
        best_peak = max(c, key=lambda x: x[1])
        clustered_timestamps.append(round(best_peak[0], 2))

    return clustered_timestamps


def detect_audio_events(
    video_path: str,
    temp_dir: Optional[str] = None,
    sample_rate: int = 16000,
    window_sec: float = 0.25,
    hop_sec: float = 0.10,
    min_db: float = -26.0,
    peak_factor: float = 2.2,
    cluster_gap: float = 15.0
) -> Tuple[List[float], str]:
    """
    Unified high-level Fast Pass function:
    1. Demuxes audio to temporary WAV
    2. Calculates sliding RMS energy profile
    3. Detects volume spikes
    4. Clusters proximate spikes into event timestamps
    Returns (clustered_timestamps, temp_wav_path).
    """
    if temp_dir is None:
        temp_dir = os.path.join(os.path.dirname(os.path.abspath(video_path)), "temp_audio")
    os.makedirs(temp_dir, exist_ok=True)

    video_name = Path(video_path).stem
    temp_wav = os.path.join(temp_dir, f"audio_{video_name}.wav")

    extract_audio_track(video_path, temp_wav, sample_rate=sample_rate)
    samples, sr = load_wav_samples(temp_wav)

    timestamps, rms = compute_sliding_rms(samples, sr, window_sec=window_sec, hop_sec=hop_sec)
    raw_peaks = detect_audio_spikes(timestamps, rms, min_db=min_db, peak_factor=peak_factor)
    clustered_peaks = cluster_timestamps(raw_peaks, min_cluster_gap=cluster_gap)

    print(f"[+] Audio Analysis Complete: Found {len(raw_peaks)} raw audio spikes -> {len(clustered_peaks)} clustered event markers.")
    return clustered_peaks, temp_wav
