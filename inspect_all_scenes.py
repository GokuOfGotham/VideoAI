import os
import sys

from video_scan_utils import DEFAULT_VIDEO, OUTPUT_DIR, extract_frames, frame_timestamp

INTERVAL = 2.0  # one thumbnail every two seconds
THUMBS_DIRNAME = "scene_thumbs"


def dump_thumbs(video_path=DEFAULT_VIDEO):
    output_dir = os.path.join(OUTPUT_DIR, THUMBS_DIRNAME)

    files = extract_frames(video_path, output_dir, fps_filter="1/2", prefix="thumb")
    print(f"Dumped {len(files)} thumbnails (sampled every {INTERVAL:g} seconds):")
    for f in files:
        print(f"  - {frame_timestamp(f, INTERVAL):g}s: {f}")
    return files


if __name__ == "__main__":
    dump_thumbs(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_VIDEO)
