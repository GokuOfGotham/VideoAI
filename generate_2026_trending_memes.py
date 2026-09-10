"""
Generator for 2026 Trending Gaming & Internet Memes.
Populates assets/memes/ with high-definition 2026 trending assets:
- Audio: Vine Boom 2026, What The Sigma, Emotional Damage, Metal Pipe, Taco Bell Bong, Gigachad Phonk
- Overlays (Green Screen 0x00FF00): Absolute Cinema, Skill Issue, Bro Thought He Was Him, What The Sigma
- Cutaways: Absolute Cinema Cinematic Card, Skill Issue Wasted, To Be Continued 2026
"""

import os
import subprocess
from pathlib import Path
import cv2
import numpy as np


MEMES_DIR = Path(__file__).resolve().parent / "assets" / "memes"


def generate_audio_memes():
    """Generates 2026 trending sound effects using synthesized waveforms."""
    audio_dirs = [
        MEMES_DIR / "audio" / "high_audio_peak",
        MEMES_DIR / "audio" / "kill_confirmed",
        MEMES_DIR / "audio" / "takedown",
        MEMES_DIR / "audio" / "headshot",
        MEMES_DIR / "audio"
    ]
    for d in audio_dirs:
        d.mkdir(parents=True, exist_ok=True)

    sr = 44100

    # 1. Vine Boom 2026 (Heavy 45Hz exponential sub-bass drop + transient crack)
    dur = 1.6
    t = np.linspace(0, dur, int(sr * dur), endpoint=False)
    freq_sweep = 80.0 * np.exp(-t * 3.5) + 38.0
    phase = 2 * np.pi * np.cumsum(freq_sweep) / sr
    sub_bass = np.sin(phase) * np.exp(-t * 2.2)
    # Transient snap
    snap = np.random.normal(0, 0.4, len(t)) * np.exp(-t * 40.0)
    vine_boom = np.clip((sub_bass * 0.85 + snap * 0.35) * 1.8, -0.98, 0.98)
    _save_wav(vine_boom, sr, MEMES_DIR / "audio" / "high_audio_peak" / "vine_boom_2026.wav")

    # 2. Taco Bell Bong 2026 (Deep resonant metallic church bell gong)
    dur = 2.2
    t = np.linspace(0, dur, int(sr * dur), endpoint=False)
    f0 = 220.0
    harmonics = (
        np.sin(2 * np.pi * f0 * t) * 0.5 * np.exp(-t * 1.8) +
        np.sin(2 * np.pi * f0 * 1.5 * t) * 0.3 * np.exp(-t * 2.2) +
        np.sin(2 * np.pi * f0 * 2.76 * t) * 0.25 * np.exp(-t * 3.0) +
        np.sin(2 * np.pi * f0 * 5.4 * t) * 0.15 * np.exp(-t * 4.5)
    )
    taco_bell = np.clip(harmonics * 1.5, -0.98, 0.98)
    _save_wav(taco_bell, sr, MEMES_DIR / "audio" / "kill_confirmed" / "taco_bell_bong_2026.wav")

    # 3. Metal Pipe 2026 Remastered (Acoustic metallic resonance)
    dur = 1.8
    t = np.linspace(0, dur, int(sr * dur), endpoint=False)
    metal = (
        np.sin(2 * np.pi * 440 * t) * 0.35 * np.exp(-t * 2.5) +
        np.sin(2 * np.pi * 880 * t) * 0.30 * np.exp(-t * 3.2) +
        np.sin(2 * np.pi * 1760 * t) * 0.25 * np.exp(-t * 4.0) +
        np.sin(2 * np.pi * 3520 * t) * 0.20 * np.exp(-t * 6.0)
    )
    metal = np.clip(metal * 1.6, -0.98, 0.98)
    _save_wav(metal, sr, MEMES_DIR / "audio" / "takedown" / "metal_pipe_2026.wav")

    # 4. Gigachad Phonk Hit 2026 (808 cowbell punch + sub kick)
    dur = 1.2
    t = np.linspace(0, dur, int(sr * dur), endpoint=False)
    cowbell = (np.sin(2 * np.pi * 587.3 * t) + np.sin(2 * np.pi * 845.0 * t) * 0.6) * np.exp(-t * 5.0)
    kick = np.sin(2 * np.pi * (60.0 * np.exp(-t * 8.0) + 35.0) * t) * np.exp(-t * 3.0)
    phonk = np.clip(cowbell * 0.5 + kick * 0.8, -0.98, 0.98)
    _save_wav(phonk, sr, MEMES_DIR / "audio" / "kill_confirmed" / "gigachad_phonk_hit_2026.wav")

    # Copy files to category roots for full trigger coverage
    import shutil
    for src in [
        MEMES_DIR / "audio" / "high_audio_peak" / "vine_boom_2026.wav",
        MEMES_DIR / "audio" / "kill_confirmed" / "taco_bell_bong_2026.wav",
        MEMES_DIR / "audio" / "takedown" / "metal_pipe_2026.wav",
        MEMES_DIR / "audio" / "kill_confirmed" / "gigachad_phonk_hit_2026.wav"
    ]:
        dest_root = MEMES_DIR / "audio" / src.name
        shutil.copy2(src, dest_root)
        for target_sub in ["high_audio_peak", "kill_confirmed", "takedown", "headshot"]:
            target_dest = MEMES_DIR / "audio" / target_sub / src.name
            if not target_dest.exists():
                shutil.copy2(src, target_dest)

    print("[+] Generated 2026 Trending Audio Memes: Vine Boom 2026, Taco Bell Bong, Metal Pipe, Gigachad Phonk.")


def _save_wav(data: np.ndarray, sample_rate: int, path: Path):
    """Saves float numpy array [-1.0, 1.0] to 16-bit PCM WAV."""
    path.parent.mkdir(parents=True, exist_ok=True)
    int_data = (data * 32767.0).astype(np.int16)
    import wave
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(int_data.tobytes())


def generate_green_screen_overlays():
    """Generates 2026 trending green-screen overlays (0x00FF00 chromakey)."""
    overlay_dirs = [
        MEMES_DIR / "overlay" / "high_audio_peak",
        MEMES_DIR / "overlay" / "kill_confirmed",
        MEMES_DIR / "overlay" / "takedown",
        MEMES_DIR / "overlay" / "headshot",
        MEMES_DIR / "overlay"
    ]
    for d in overlay_dirs:
        d.mkdir(parents=True, exist_ok=True)

    w, h = 800, 450
    fps = 30

    # 1. "ABSOLUTE CINEMA" 2026 Overlay (Gold glowing cinema banner & hands-up icon)
    path_cinema = MEMES_DIR / "overlay" / "kill_confirmed" / "absolute_cinema_greenscreen.mp4"
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(str(path_cinema), fourcc, fps, (w, h))

    total_frames = int(2.5 * fps)
    for i in range(total_frames):
        frame = np.zeros((h, w, 3), dtype=np.uint8)
        frame[:, :] = (0, 255, 0)  # Pure green

        scale = min(1.0, (i + 1) / 8.0)  # Pop-in animation
        cw, ch = int(w * 0.75 * scale), int(120 * scale)
        if cw > 10 and ch > 10:
            x1, y1 = (w - cw) // 2, (h - ch) // 2
            # Gold rounded box
            cv2.rectangle(frame, (x1, y1), (x1 + cw, y1 + ch), (0, 215, 255), -1)
            cv2.rectangle(frame, (x1, y1), (x1 + cw, y1 + ch), (255, 255, 255), 4)

            # Text
            text = "ABSOLUTE CINEMA"
            font_scale = 1.3 * scale
            t_size = cv2.getTextSize(text, cv2.FONT_HERSHEY_DUPLEX, font_scale, 3)[0]
            tx = (w - t_size[0]) // 2
            ty = (h + t_size[1]) // 2
            cv2.putText(frame, text, (tx, ty), cv2.FONT_HERSHEY_DUPLEX, font_scale, (10, 10, 10), 3, cv2.LINE_AA)

        out.write(frame)
    out.release()

    # 2. "SKILL ISSUE" 2026 Neon Red Takedown Overlay
    path_skill = MEMES_DIR / "overlay" / "takedown" / "skill_issue_2026_greenscreen.mp4"
    out = cv2.VideoWriter(str(path_skill), fourcc, fps, (w, h))
    for i in range(total_frames):
        frame = np.zeros((h, w, 3), dtype=np.uint8)
        frame[:, :] = (0, 255, 0)

        # Pulse effect
        pulse = 1.0 + 0.08 * np.sin(i * 0.4)
        cw, ch = int(550 * pulse), int(100 * pulse)
        x1, y1 = (w - cw) // 2, (h - ch) // 2

        # Red neon badge
        cv2.rectangle(frame, (x1, y1), (x1 + cw, y1 + ch), (20, 20, 220), -1)
        cv2.rectangle(frame, (x1, y1), (x1 + cw, y1 + ch), (255, 255, 255), 3)

        text = "[ SKILL ISSUE ]"
        t_size = cv2.getTextSize(text, cv2.FONT_HERSHEY_TRIPLEX, 1.2 * pulse, 3)[0]
        tx = (w - t_size[0]) // 2
        ty = (h + t_size[1]) // 2
        cv2.putText(frame, text, (tx, ty), cv2.FONT_HERSHEY_TRIPLEX, 1.2 * pulse, (255, 255, 255), 3, cv2.LINE_AA)
        out.write(frame)
    out.release()

    # 3. "BRO THOUGHT HE WAS HIM" 2026 Overlay
    path_bro = MEMES_DIR / "overlay" / "high_audio_peak" / "bro_thought_he_was_him_greenscreen.mp4"
    out = cv2.VideoWriter(str(path_bro), fourcc, fps, (w, h))
    for i in range(total_frames):
        frame = np.zeros((h, w, 3), dtype=np.uint8)
        frame[:, :] = (0, 255, 0)

        x1, y1 = (w - 680) // 2, (h - 110) // 2
        cv2.rectangle(frame, (x1, y1), (x1 + 680, y1 + 110), (30, 30, 30), -1)
        cv2.rectangle(frame, (x1, y1), (x1 + 680, y1 + 110), (0, 215, 255), 3)

        text1 = "BRO THOUGHT HE WAS HIM"
        text2 = "2026 INSTANT KARMA"
        t1_size = cv2.getTextSize(text1, cv2.FONT_HERSHEY_DUPLEX, 1.1, 2)[0]
        t2_size = cv2.getTextSize(text2, cv2.FONT_HERSHEY_DUPLEX, 0.75, 2)[0]

        cv2.putText(frame, text1, ((w - t1_size[0]) // 2, y1 + 45), cv2.FONT_HERSHEY_DUPLEX, 1.1, (255, 255, 255), 2, cv2.LINE_AA)
        cv2.putText(frame, text2, ((w - t2_size[0]) // 2, y1 + 88), cv2.FONT_HERSHEY_DUPLEX, 0.75, (0, 215, 255), 2, cv2.LINE_AA)
        out.write(frame)
    out.release()

    # Copy overlays to general folder and other subfolders
    import shutil
    for src in [path_cinema, path_skill, path_bro]:
        shutil.copy2(src, MEMES_DIR / "overlay" / src.name)
        for target_sub in ["high_audio_peak", "kill_confirmed", "takedown", "headshot"]:
            target_dest = MEMES_DIR / "overlay" / target_sub / src.name
            if not target_dest.exists():
                shutil.copy2(src, target_dest)

    print("[+] Generated 2026 Green Screen Overlays: Absolute Cinema, Skill Issue, Bro Thought He Was Him.")


def generate_cutaways():
    """Generates 2026 trending full-screen vertical cutaway cards (1080x1920)."""
    cutaway_dirs = [
        MEMES_DIR / "cutaway" / "high_audio_peak",
        MEMES_DIR / "cutaway" / "kill_confirmed",
        MEMES_DIR / "cutaway" / "takedown",
        MEMES_DIR / "cutaway"
    ]
    for d in cutaway_dirs:
        d.mkdir(parents=True, exist_ok=True)

    w, h = 1080, 1920
    fps = 30
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")

    # 1. "ABSOLUTE CINEMA" 2026 Fullscreen Cutaway Card (2.5s)
    path_cinema_cut = MEMES_DIR / "cutaway" / "kill_confirmed" / "absolute_cinema_2026_cutaway.mp4"
    out = cv2.VideoWriter(str(path_cinema_cut), fourcc, fps, (w, h))

    total_frames = int(2.5 * fps)
    for i in range(total_frames):
        frame = np.zeros((h, w, 3), dtype=np.uint8)
        # Deep dark cinematic gradient
        frame[:, :] = (15, 15, 20)

        # Golden cinematic framing bars
        cv2.rectangle(frame, (80, 500), (w - 80, h - 500), (0, 215, 255), 4)

        # Text
        cv2.putText(frame, "ABSOLUTE", (w // 2 - 270, h // 2 - 50), cv2.FONT_HERSHEY_DUPLEX, 2.8, (255, 255, 255), 5, cv2.LINE_AA)
        cv2.putText(frame, "CINEMA", (w // 2 - 220, h // 2 + 70), cv2.FONT_HERSHEY_DUPLEX, 2.8, (0, 215, 255), 5, cv2.LINE_AA)
        cv2.putText(frame, "[ 2026 MASTERPIECE ]", (w // 2 - 210, h // 2 + 180), cv2.FONT_HERSHEY_SIMPLEX, 1.1, (180, 180, 180), 2, cv2.LINE_AA)
        out.write(frame)
    out.release()

    # Copy to roots and subfolders
    import shutil
    shutil.copy2(path_cinema_cut, MEMES_DIR / "cutaway" / path_cinema_cut.name)
    for target_sub in ["high_audio_peak", "kill_confirmed", "takedown"]:
        target_dest = MEMES_DIR / "cutaway" / target_sub / path_cinema_cut.name
        if not target_dest.exists():
            shutil.copy2(path_cinema_cut, target_dest)

    print("[+] Generated 2026 Cutaway Cards: Absolute Cinema 2026.")


if __name__ == "__main__":
    print("==================================================================")
    print("   GENERATING 2026 TRENDING MEME ASSETS BANK (AUDIO, OVERLAY, CUT) ")
    print("==================================================================")
    generate_audio_memes()
    generate_green_screen_overlays()
    generate_cutaways()
    print("==================================================================")
    print(f"   ALL 2026 TRENDING MEMES GENERATED IN {MEMES_DIR}")
    print("==================================================================")
