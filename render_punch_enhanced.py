import os, subprocess

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.getenv("OUTPUT_DIR", os.path.join(PROJECT_ROOT, "output"))
MUSIC_DIR = os.getenv("EPIDEMIC_MUSIC_DIR", os.path.join(PROJECT_ROOT, "assets", "epidemic_sound"))


out_dir = OUTPUT_DIR
os.makedirs(out_dir, exist_ok=True)

music_src = os.path.join(MUSIC_DIR, "Final_Frontier.mp3")

# Video 1: 4K Movie Ace Chemicals continuous single scene
video_4k = r'M:\Videos\Gaming\PlayStation 5\Batman Arkham Knight\Batman_ Arkham Knight (The Movie).mp4'
out_v1 = os.path.join(out_dir, 'Batman_60s_Brutal_Punches_Enhanced_AceChemicals.mp4')

# Video 2: Unbroken Close-Quarters Militia Brawl (continuous 58s room fight)
video_troops = r'M:\Videos\Gaming\PlayStation 5\Batman Arkham Knight\Shorts\Batman vs Troops.mp4'
out_v2 = os.path.join(out_dir, 'Batman_60s_Brutal_Punches_Enhanced_TroopsBrawl.mp4')

def render_punch_enhanced(video_src, seek_time, duration, music_src, out_file):
    # Audio Punch Filter:
    # 1. Bass boost at 85Hz (+9dB) for heavy chest-thumping impact thuds
    # 2. Treble/Snap boost at 3200Hz (+4.5dB) for bone-breaking knuckle cracks
    # 3. Dynamic compander for punch transients
    # Visual Punch Filter:
    # 1. Gritty Dark Knight contrast & saturation boost (contrast=1.14, saturation=1.10)
    # 2. Crisp unsharp filter (unsharp=5:5:0.9) to make hit sparks and suit details pop
    filter_complex = f'''
    [0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,fps=30,eq=contrast=1.14:brightness=-0.01:saturation=1.10,unsharp=5:5:0.9:5:5:0.0,format=yuv420p,fade=t=out:st={duration-1.5}:d=1.5[v_out];
    [0:a]bass=g=9:f=85:w=0.6,equalizer=f=3200:width_type=o:width=1.2:g=4.5,compand=attacks=0.01:decays=0.1:points=-80/-80|-40/-30|-20/-10|0/0:gain=3,volume=1.15,asetpts=PTS-STARTPTS[a_punches];
    [1:a]volume=0.68,atrim=start=0.0:end={duration},asetpts=PTS-STARTPTS[a_music];
    [a_punches][a_music]amix=inputs=2:duration=first:dropout_transition=2:normalize=0,afade=t=out:st={duration-1.5}:d=1.5[a_out]
    '''

    seek_args = ['-ss', seek_time] if seek_time else []

    cmd = [
        'ffmpeg', '-y',
        *seek_args,
        '-i', video_src,
        '-i', music_src,
        '-filter_complex', filter_complex,
        '-map', '[v_out]',
        '-map', '[a_out]',
        '-c:v', 'libx264',
        '-profile:v', 'high',
        '-level:v', '4.1',
        '-pix_fmt', 'yuv420p',
        '-preset', 'fast',
        '-crf', '18',
        '-c:a', 'aac',
        '-b:a', '256k',
        '-t', str(duration),
        '-movflags', '+faststart',
        out_file
    ]

    print(f'[*] Rendering Punch-Enhanced Master: {out_file}...')
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode == 0:
        print(f'[+] SUCCESS: {out_file} ({os.path.getsize(out_file)} bytes)')
    else:
        print(f'[!] Error:\n{res.stderr[-800:]}')

render_punch_enhanced(video_4k, '00:36:00', 60.0, music_src, out_v1)
render_punch_enhanced(video_troops, None, 58.0, music_src, out_v2)
