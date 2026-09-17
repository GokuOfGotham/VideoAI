"""VideoAI editing room: the departments a finishing suite needs beyond audio sourcing.

Epidemic (music, effects, voices) and the broadcast graphics were already in
the toolkit. This package adds the remaining roles of a post-production room,
each as plain functions over FFmpeg, OpenCV, numpy and faster-whisper so they
run locally and are testable with synthetic media:

  ingest    Assistant editor: transcribe_media, sync_multicam, detect_silence,
            generate_proxies.
  timeline  Picture editor: a JSON timeline, get_timeline_state,
            apply_edit_action, build_assembly, export_xml (FCPXML), and a
            bridge to edit_tools' segment renderer.
  visual    VFX and graphics: search_visual_broll, generate_captions,
            auto_reframe (16:9 to 9:16 subject tracking).
  audio     Audio mixer: clean_dialogue, apply_audio_ducking, generate_adr.
  color     Colorist: match_color, apply_lut, built-in looks.

Every tool returns a JSON-serialisable report. Nothing here bypasses the
production policy: a timeline still renders through edit_tools/graphics_tool,
and ADR uses the approved Cedar preset rather than a cloned voice.
"""

from .common import EditRoomError, ffprobe_json, media_duration, run_ffmpeg

__all__ = ["EditRoomError", "ffprobe_json", "media_duration", "run_ffmpeg"]
