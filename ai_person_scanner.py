import os
import sys

from ultralytics import YOLO

from video_scan_utils import DEFAULT_VIDEO, OUTPUT_DIR, open_video, to_segments

MODEL_NAME = os.getenv("YOLO_MODEL", "yolov8n.pt")


def get_pure_aircraft_segments(video_path: str, confidence_threshold: float = 0.25,
                               samples_per_second: float = 4.0):
    """
    Scans a video using YOLOv8 to detect any person, returning video segments
    containing no detected people.
    """
    print("\n=======================================================")
    print("   YOLOV8 AI NEURAL SCANNER (0% HUMAN / 0% BODY PARTS) ")
    print("=======================================================")
    print("[*] Loading YOLOv8 Neural Network model...")
    model = YOLO(MODEL_NAME)

    cap, fps, total_frames, duration = open_video(video_path)
    print(f"[*] Analyzing video: {video_path} ({duration:.2f}s, {fps:.1f} fps)")

    # Sample roughly samples_per_second times per second, but never skip
    # fewer than one frame (a zero step would divide by zero below).
    step = max(1, int(round(fps / samples_per_second)))
    sample_interval = step / fps
    print(f"[*] Sampling every {step} frame(s) - one sample per {sample_interval:.3f}s")

    frame_idx = 0
    human_timestamps = []
    clean_timestamps = []

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            frame_idx += 1

            if frame_idx % step:
                continue

            sec = round(frame_idx / fps, 2)
            results = model(frame, verbose=False, conf=confidence_threshold)[0]

            has_human = any(
                model.names[int(box.cls[0])] == "person" for box in results.boxes
            )

            if has_human:
                human_timestamps.append(sec)
            else:
                clean_timestamps.append(sec)
    finally:
        cap.release()

    clean_segments = to_segments(clean_timestamps, sample_interval)

    print("[+] AI Neural Scan Complete!")
    print(f"[!] Human-detected samples ({len(human_timestamps)}): {human_timestamps[:10]}...")
    print(f"[+] Pure Aircraft Segments (0% Human Bodies/Parts): {clean_segments}")
    print("=======================================================\n")

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    out_file = os.path.join(OUTPUT_DIR, "yolo_clean_segments.txt")
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(str(clean_segments))
    print(f"[+] Saved clean segments to: {out_file}")
    return clean_segments


if __name__ == "__main__":
    v_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_VIDEO
    get_pure_aircraft_segments(v_path)
