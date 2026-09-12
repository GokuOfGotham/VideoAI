import os
import subprocess
import sys

print("=========================================================================")
print("Please edit this script to configure the exact timestamps before running!")
print("=========================================================================")

# ==============================================================================
# 1. SOURCE TIMESTAMPS (IN SECONDS)
# Configure these based on the original unedited video file.
# ==============================================================================
T_BANE_SPEECH_START = 188.0
T_BANE_SPEECH_END = 196.0

T_FREEFALL_START = 197.0
T_FREEFALL_END = 199.0     # The 2 seconds Batman is falling

T_GORDON_START = 250.0
T_GORDON_END = 256.0

T_END = 257.5              # Shortened to avoid 4 seconds of black screen at the end!

# ==============================================================================
# 2. TEXT OVERLAY TIMESTAMPS (IN SOURCE SECONDS)
# ==============================================================================
TEXT1_START, TEXT1_END = 170.0, 176.0  # "The cave broke his body."
TEXT2_START, TEXT2_END = 180.0, 186.0  # "This broke his legend."
TEXT3_START, TEXT3_END = 190.0, 195.0  # "Bane wanted an audience."
TEXT4_START, TEXT4_END = 251.0, 257.0  # "Gotham's god has fallen."


# ==============================================================================
# FILE PATHS
# ==============================================================================
VIDEO_SRC = r"M:\Videos\Gaming\Bane Breaks Batman's Back  (DC Animated Movie - Batman_ Knightfall Part 1 - 2026).mp4"
IMPACT_SFX = r"A:\ai\VideoAI\assets\epidemic_sound\sfx\Fight__Impact__Punch__Hit__Hard__Variations.mp3"
FONT_FILE = "assets/fonts/Montserrat-Black.ttf"
OUT_DIR = r"A:\ai\VideoAI\output"

os.makedirs(OUT_DIR, exist_ok=True)

def map_time(t):
    if t <= T_FREEFALL_START:
        res = t
    elif t <= T_FREEFALL_END:
        res = T_FREEFALL_START + (t - T_FREEFALL_START) * 2.0
    else:
        slowmo_extra_time = (T_FREEFALL_END - T_FREEFALL_START) * 1.0
        res = t + slowmo_extra_time
    return res - 165.0

def render_video(is_short=False):
    out_name = "The_Fall_of_a_God_Short.mp4" if is_short else "The_Fall_of_a_God_Longform.mp4"
    out_path = os.path.join(OUT_DIR, out_name)
    
    new_total_duration = map_time(T_END)
    fade_out_start = new_total_duration - 2.0

    # 1. Base Framing & Color Grading
    # Add unsharp for extra sharpness, and adjust colors. Reduced contrast so it's not too dark!
    cg = "eq=contrast=1.05:brightness=0.0:saturation=0.85:gamma_b=1.1,unsharp=5:5:1.0:5:5:0.0"
    
    if is_short:
        # Scale to fill 1080x1920 (9:16) and crop center
        framing = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1"
        base_filter = f"{framing},{cg}"
        final_w, final_h = 1080, 1920
    else:
        base_filter = f"{cg}"
        final_w, final_h = 1920, 1080

    T_START = 165.0

    # Segment 1 (Start -> Freefall)
    v1 = f"[0:v]trim={T_START}:{T_FREEFALL_START},setpts=PTS-STARTPTS,{base_filter}[v1_base];"
    a1 = f"[0:a]atrim={T_START}:{T_FREEFALL_START},asetpts=PTS-STARTPTS[a1_base];"
    v1 += f"[v1_base]copy[v1];"
    a1 += f"[a1_base]volume='if(between(t,{T_BANE_SPEECH_START-165.0},{T_BANE_SPEECH_END-165.0}),2.0,1.0)'[a1];"

    # Segment 2 (Freefall -> 0.5x slowmo, silent audio)
    v2 = f"[0:v]trim={T_FREEFALL_START}:{T_FREEFALL_END},setpts=2.0*(PTS-STARTPTS),{base_filter}[v2];"
    a2 = f"[0:a]atrim={T_FREEFALL_START}:{T_FREEFALL_END},asetpts=PTS-STARTPTS,atempo=0.5,volume=0[a2];"

    # Segment 3 (Impact -> Gordon)
    shake_dur = 0.4
    # Shake effect: Scale up slightly by 1.05x so we can shake the crop window without hitting black borders
    v3 = f"[0:v]trim={T_FREEFALL_END}:{T_GORDON_START},setpts=PTS-STARTPTS,{base_filter}," \
         f"scale=iw*1.05:ih*1.05,crop=iw/1.05:ih/1.05:'(in_w-out_w)/2+if(lte(t,{shake_dur}),sin(t*40)*15,0)':'(in_h-out_h)/2+if(lte(t,{shake_dur}),cos(t*35)*15,0)'[v3];"
    a3 = f"[0:a]atrim={T_FREEFALL_END}:{T_GORDON_START},asetpts=PTS-STARTPTS[a3];"

    # Segment 4 (Gordon -> Zoom-in)
    dur4 = T_GORDON_END - T_GORDON_START
    frames4 = int(dur4 * 24)
    # Smooth zoompan by incrementing zoom by a smaller, smoother amount
    v4 = f"[0:v]trim={T_GORDON_START}:{T_GORDON_END},setpts=PTS-STARTPTS,{base_filter}," \
         f"zoompan=z='min(zoom+0.0015,1.2)':d={frames4}:s={final_w}x{final_h}:fps=24[v4];"
    a4 = f"[0:a]atrim={T_GORDON_START}:{T_GORDON_END},asetpts=PTS-STARTPTS[a4];"

    # Segment 5 (Gordon End -> End)
    v5 = f"[0:v]trim={T_GORDON_END}:{T_END},setpts=PTS-STARTPTS,{base_filter}[v5];"
    a5 = f"[0:a]atrim={T_GORDON_END}:{T_END},asetpts=PTS-STARTPTS[a5];"

    concat = "[v1][a1][v2][a2][v3][a3][v4][a4][v5][a5]concat=n=5:v=1:a=1[v_cat][a_cat];"

    new_impact_time_ms = int(map_time(T_FREEFALL_END) * 1000)
    mix_sfx = f"[1:a]volume=2.0,adelay={new_impact_time_ms}|{new_impact_time_ms}[sfx];" \
              f"[a_cat][sfx]amix=inputs=2:duration=first:dropout_transition=2[a_mix];"

    texts = [
        (TEXT1_START, TEXT1_END, "The cave broke his body."),
        (TEXT2_START, TEXT2_END, "This broke his legend."),
        (TEXT3_START, TEXT3_END, "Bane wanted an audience."),
        (TEXT4_START, TEXT4_END, "Gotham's god has fallen.")
    ]

    text_filters = "[v_cat]"
    for i, (t_start, t_end, txt) in enumerate(texts):
        nt_start = map_time(t_start)
        nt_end = map_time(t_end)
        # Smoother fade-in typewriter glitch: Opacity fades in rapidly but stutters
        alpha_expr = f"if(lt(t,{nt_start+0.4}), abs(sin((t-{nt_start})*20)), 1)"
        font_color = "white"
        txt_safe = txt.replace("'", "’")
        
        # Make font slightly smaller for vertical format so it doesn't clip
        fs = 56 if is_short else 72
        y_offset = "h-th-250" if is_short else "h-th-150"
        
        drawtext = f"drawtext=fontfile='{FONT_FILE}':text='{txt_safe}':fontcolor={font_color}:fontsize={fs}:" \
                   f"x='(w-tw)/2':y='{y_offset}':enable='between(t,{nt_start},{nt_end})':alpha='{alpha_expr}'"
        
        if i == 0:
            text_filters += f"{drawtext}[v_t1];"
        elif i == len(texts) - 1:
            text_filters += f"[v_t{i}]{drawtext}[v_t_out];"
        else:
            text_filters += f"[v_t{i}]{drawtext}[v_t{i+1}];"

    fade_filter = f"[v_t_out]fade=t=out:st={fade_out_start}:d=2.0[v_final];" \
                  f"[a_mix]afade=t=out:st={fade_out_start}:d=2.0[a_final]"

    filter_complex = f"{v1}\n{a1}\n{v2}\n{a2}\n{v3}\n{a3}\n{v4}\n{a4}\n{v5}\n{a5}\n{concat}\n{mix_sfx}\n{text_filters}\n{fade_filter}"

    cmd = [
        "ffmpeg", "-y",
        "-i", VIDEO_SRC,
        "-i", IMPACT_SFX,
        "-filter_complex", filter_complex,
        "-map", "[v_final]",
        "-map", "[a_final]",
        "-c:v", "libx264",
        "-profile:v", "high",
        "-level:v", "4.1",
        "-pix_fmt", "yuv420p",
        "-preset", "fast",
        "-crf", "18",
        "-c:a", "aac",
        "-b:a", "256k",
        "-movflags", "+faststart",
        out_path
    ]

    print(f"[*] Rendering {out_name}...")
    res = subprocess.run(cmd, capture_output=True, text=True)

    if res.returncode == 0:
        print(f"[+] SUCCESS! Saved: {out_path}")
    else:
        print(f"[!] ERROR rendering {out_name}! FFmpeg Output:\n{res.stderr[-2000:]}")

if __name__ == "__main__":
    # Render both versions
    print("[*] Starting Longform Render (16:9)...")
    render_video(is_short=False)
    
    print("[*] Starting Shortform Render (9:16)...")
    render_video(is_short=True)
    
    print("[*] All jobs finished.")
