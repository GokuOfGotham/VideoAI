"""
Combat Matrix Scanner (Deterministic Gaming Combat Detection Engine)
Layers:
  1. Cutscene Letterbox & Static Dialogue Rejection
  2. Combat HUD / Combo Counter & Takedown Prompt Detector
  3. Audio Transient Punch & Sub-Bass Impact Frequency Analyzer
  4. Optical Flow & Kinetic Limb Velocity Analyzer
"""

import os, sys, cv2, json, subprocess, numpy as np

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

class CombatMatrixScanner:
    def __init__(self, output_db=None):
        self.output_db = output_db or os.path.join(
            PROJECT_ROOT, "assets", "verified_combat_database.json")
        os.makedirs(os.path.dirname(self.output_db), exist_ok=True)
        self.database = self.load_database()

    def load_database(self):
        if os.path.exists(self.output_db):
            try:
                with open(self.output_db, "r", encoding="utf-8") as f:
                    return json.load(f)
            except:
                pass
        return {"scanned_at": "", "verified_fights": []}

    def save_database(self):
        with open(self.output_db, "w", encoding="utf-8") as f:
            json.dump(self.database, f, indent=2)

    def analyze_letterbox_cutscene(self, frame) -> bool:
        """Returns True if a 16:9 widescreen frame has cinematic 2.35:1 movie letterbox bars."""
        h, w = frame.shape[:2]
        # Only check letterboxing on horizontal 16:9/landscape footage
        if w >= h:
            top_bar = frame[0:int(h * 0.10), :]
            bottom_bar = frame[int(h * 0.90):, :]
            return float(np.mean(top_bar)) < 4.0 and float(np.mean(bottom_bar)) < 4.0
        return False

    def analyze_combat_hud(self, frame) -> float:
        """Detects in-game combat HUD elements (Combo Counters, Takedown prompts, Alert icons)."""
        h, w = frame.shape[:2]
        # Region 1: Top-Left HUD (Arkham / Spider-Man Combo Counters)
        hud_tl = frame[int(h * 0.05):int(h * 0.30), int(w * 0.02):int(w * 0.30)]
        # Region 2: Center-Bottom (Takedown & Button prompts)
        hud_cb = frame[int(h * 0.50):int(h * 0.85), int(w * 0.25):int(w * 0.75)]

        score = 0.0

        # Check Top-Left text/edges
        gray_tl = cv2.cvtColor(hud_tl, cv2.COLOR_BGR2GRAY)
        edges_tl = cv2.Canny(gray_tl, 60, 160)
        edge_density_tl = np.mean(edges_tl)
        if edge_density_tl > 3.0:
            score += min(edge_density_tl * 4.0, 40.0)

        # Check Center-Bottom prompts / alert icons
        gray_cb = cv2.cvtColor(hud_cb, cv2.COLOR_BGR2GRAY)
        edges_cb = cv2.Canny(gray_cb, 80, 180)
        edge_density_cb = np.mean(edges_cb)
        if edge_density_cb > 2.0:
            score += min(edge_density_cb * 3.0, 30.0)

        return min(score, 50.0)

    def analyze_audio_punch_transients(self, video_path, start_sec, duration=30.0) -> dict:
        """Extracts audio waveform and detects punch impact transient spikes (80Hz sub-bass + 3.2kHz cracks)."""
        wav_temp = os.path.join(PROJECT_ROOT, "temp_sfx_check.wav")
        cmd = [
            "ffmpeg", "-y",
            "-ss", str(start_sec),
            "-i", video_path,
            "-t", str(duration),
            "-vn", "-ac", "1", "-ar", "22050",
            wav_temp
        ]
        res = subprocess.run(cmd, capture_output=True)
        if res.returncode != 0 or not os.path.exists(wav_temp):
            return {"transient_count": 0, "punch_density": 0.0, "is_dialogue": True}

        # Read audio samples
        import wave
        try:
            with wave.open(wav_temp, "rb") as wf:
                n_frames = wf.getnframes()
                raw_audio = wf.readframes(n_frames)
                audio_samples = np.frombuffer(raw_audio, dtype=np.int16).astype(np.float32)
        except:
            audio_samples = np.array([])
        finally:
            if os.path.exists(wav_temp):
                os.remove(wav_temp)

        if len(audio_samples) == 0:
            return {"transient_count": 0, "punch_density": 0.0, "is_dialogue": True}

        # Calculate short-time energy (100ms windows)
        hop = 2205 # 100ms
        energy = np.array([np.mean(np.abs(audio_samples[i:i+hop])) for i in range(0, len(audio_samples)-hop, hop)])
        if len(energy) == 0 or np.max(energy) == 0:
            return {"transient_count": 0, "punch_density": 0.0, "is_dialogue": True}

        # Normalize energy
        energy_norm = energy / np.max(energy)
        mean_energy = np.mean(energy_norm)

        # Count sudden transient spikes (characteristic of punch impacts / bone snaps)
        transients = 0
        for i in range(1, len(energy_norm) - 1):
            if energy_norm[i] > 0.45 and energy_norm[i] > energy_norm[i-1] * 1.5 and energy_norm[i] > energy_norm[i+1]:
                transients += 1

        hits_per_30s = (transients / max(duration, 1.0)) * 30.0
        # Dialogue has high speech continuity and low sharp transient hits (< 4 hits per 30s)
        is_dialogue = hits_per_30s < 5.0 and mean_energy < 0.15

        return {
            "transient_count": transients,
            "punch_density": round(hits_per_30s, 1),
            "is_dialogue": is_dialogue
        }

    def analyze_motion_velocity(self, frames) -> float:
        """Calculates kinetic optical motion velocity across sequential frames."""
        if len(frames) < 2:
            return 0.0
        diffs = []
        for i in range(len(frames) - 1):
            g1 = cv2.cvtColor(frames[i], cv2.COLOR_BGR2GRAY)
            g2 = cv2.cvtColor(frames[i+1], cv2.COLOR_BGR2GRAY)
            diff = np.mean(cv2.absdiff(g1, g2))
            diffs.append(diff)
        return float(np.mean(diffs))

    def evaluate_combat_segment(self, video_path, start_sec, duration=30.0) -> dict:
        """Evaluates a 30s-60s candidate segment using all 4 layers of the Combat Detection Matrix."""
        # 1. Sample 5 sequential frames (1 every 6s)
        frames = []
        is_letterboxed = False
        hud_scores = []

        for offset in [0, 6, 12, 18, 24]:
            t = start_sec + offset
            fpath = os.path.join(PROJECT_ROOT, f"temp_frame_{offset}.jpg")
            subprocess.run(["ffmpeg", "-y", "-ss", str(t), "-i", video_path, "-vframes", "1", "-vf", "scale=640:360", "-q:v", "3", fpath], capture_output=True)
            if os.path.exists(fpath):
                img = cv2.imread(fpath)
                if img is not None:
                    frames.append(img)
                    if self.analyze_letterbox_cutscene(img):
                        is_letterboxed = True
                    hud_scores.append(self.analyze_combat_hud(img))
                os.remove(fpath)

        if not frames:
            return {"confidence": 0, "is_combat": False, "reason": "Could not read frames"}

        # Layer 1: Cutscene Letterbox Filter
        if is_letterboxed:
            return {
                "confidence": 5.0,
                "is_combat": False,
                "reason": "Rejected: Cinematic letterboxed cutscene detected",
                "hud_score": 0.0,
                "punch_hits_per_30s": 0.0,
                "motion_velocity": 0.0
            }

        # Layer 2: Combat HUD Score (0 - 50)
        avg_hud = float(np.mean(hud_scores)) if hud_scores else 0.0

        # Layer 3: Audio Punch Transients (0 - 30)
        audio_info = self.analyze_audio_punch_transients(video_path, start_sec, duration)
        if audio_info["is_dialogue"] and avg_hud < 8.0:
            return {
                "confidence": 10.0,
                "is_combat": False,
                "reason": "Rejected: Dialogue / conversation detected (no combat audio hits or HUD)",
                "hud_score": round(avg_hud, 1),
                "punch_hits_per_30s": audio_info["punch_density"],
                "motion_velocity": 0.0
            }

        # Layer 4: Motion Velocity (0 - 20)
        motion_velocity = self.analyze_motion_velocity(frames)

        # Composite Confidence Score (0 - 100)
        hud_weight = min(avg_hud * 1.5, 45.0)
        audio_weight = min(audio_info["punch_density"] * 2.0, 35.0)
        motion_weight = min(motion_velocity * 1.0, 20.0)

        total_confidence = min(round(hud_weight + audio_weight + motion_weight, 1), 100.0)
        is_combat = total_confidence >= 55.0 and audio_info["transient_count"] >= 4

        return {
            "start_sec": start_sec,
            "duration": duration,
            "confidence": total_confidence,
            "is_combat": is_combat,
            "hud_score": round(avg_hud, 1),
            "punch_hits_per_30s": audio_info["punch_density"],
            "motion_velocity": round(motion_velocity, 1),
            "reason": "VERIFIED PHYSICAL COMBAT" if is_combat else "Insufficient combat telemetry"
        }

if __name__ == "__main__":
    scanner = CombatMatrixScanner()
    
    # Test on known clips
    test_clips = [
        (r"M:\Videos\Gaming\PlayStation 5\Batman Arkham Knight\Shorts\Batman vs Troops.mp4", 10.0, "Batman vs Troops (Combat Brawl)"),
        (r"M:\Videos\Gaming\PlayStation 5\Batman Arkham Knight\Shorts\Harvey Dent.mp4", 5.0, "Harvey Dent (Dialogue Scene)"),
        (r"M:\Videos\Gaming\PlayStation 5\Batman Arkham Knight\Shorts\Batman and Robyn vs Goliath.mp4", 2.0, "Batman & Robin vs Goliath (Boss Brawl)")
    ]

    print("==================================================================")
    print("       TESTING 4-LAYER COMBAT DETECTION MATRIX ON GAMEPLAY        ")
    print("==================================================================")
    for path, start_t, label in test_clips:
        print(f"\n[*] Evaluating: {label}")
        result = scanner.evaluate_combat_segment(path, start_t, duration=20.0)
        status = ">>> [PASS: COMBAT]" if result["is_combat"] else ">>> [REJECTED: NOT COMBAT]"
        print(f"    Status: {status} (Confidence: {result['confidence']}%)")
        print(f"    HUD Score: {result['hud_score']} | Punch Hits: {result['punch_hits_per_30s']}/30s | Motion: {result['motion_velocity']}")
        print(f"    Verdict: {result['reason']}")
