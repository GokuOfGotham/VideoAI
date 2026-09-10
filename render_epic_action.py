import os, subprocess

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.getenv("OUTPUT_DIR", os.path.join(PROJECT_ROOT, "output"))
MUSIC_DIR = os.getenv("EPIDEMIC_MUSIC_DIR", os.path.join(PROJECT_ROOT, "assets", "epidemic_sound"))


output_v1 = os.path.join(OUTPUT_DIR, "Batman_60s_HeavyMetal_Action_Master.mp4")
output_v2 = os.path.join(OUTPUT_DIR, "Batman_60s_Blockbuster_Trailer_Master.mp4")

music_v1 = os.path.join(MUSIC_DIR, "Ten_Times_a_Hundred_Years.mp3")
music_v2 = os.path.join(MUSIC_DIR, "Sentinel_Ascend.mp3")

# Exact same 4-shot visual sequence (60.0s total)
c1 = r'M:\Videos\Gaming\PlayStation 5\Batman Arkham Knight\Shorts\Batman and Robyn vs Goliath.mp4' # 2s - 16s (14s)
c2 = r'M:\Videos\Gaming\PlayStation 5\Batman Arkham Knight\Shorts\Batman vs Troops.mp4' # 10s - 32s (22s)
c3 = r'M:\Videos\Gaming\PlayStation 5\Batman Arkham Knight\Shorts\Violent Batman.mp4' # 0s - 12s (12s)
c4 = r'M:\Videos\Gaming\PlayStation 5\Batman Arkham Knight\Shorts\Batman Warrior.mp4' # 16s - 28s (12s)

def render_with_music(music_file, output_path, music_vol=1.4, sfx_vol=0.35):
    filter_complex = f'''
    [0:v]trim=start=2.0:end=16.0,setpts=PTS-STARTPTS,scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,fps=30[v0];
    [0:a]atrim=start=2.0:end=16.0,asetpts=PTS-STARTPTS[a0];

    [1:v]trim=start=10.0:end=32.0,setpts=PTS-STARTPTS,scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,fps=30[v1];
    [1:a]atrim=start=10.0:end=32.0,asetpts=PTS-STARTPTS[a1];

    [2:v]trim=start=0.0:end=12.0,setpts=PTS-STARTPTS,scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,fps=30[v2];
    [2:a]atrim=start=0.0:end=12.0,asetpts=PTS-STARTPTS[a2];

    [3:v]trim=start=16.0:end=28.0,setpts=PTS-STARTPTS,scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,fps=30[v3];
    [3:a]atrim=start=16.0:end=28.0,asetpts=PTS-STARTPTS[a3];

    [v0][a0][v1][a1][v2][a2][v3][a3]concat=n=4:v=1:a=1[v_raw][a_game];
    [v_raw]fade=t=out:st=58.5:d=1.5[v_out];

    [a_game]volume={sfx_vol}[a_sfx];
    [4:a]volume={music_vol},atrim=start=0.0:end=60.0,asetpts=PTS-STARTPTS[a_music];
    [a_sfx][a_music]amix=inputs=2:duration=first:dropout_transition=2:normalize=0,afade=t=out:st=58.5:d=1.5[a_out]
    '''

    cmd = [
        'ffmpeg', '-y',
        '-i', c1,
        '-i', c2,
        '-i', c3,
        '-i', c4,
        '-i', music_file,
        '-filter_complex', filter_complex,
        '-map', '[v_out]',
        '-map', '[a_out]',
        '-c:v', 'libx264',
        '-preset', 'fast',
        '-crf', '18',
        '-c:a', 'aac',
        '-b:a', '256k',
        '-t', '60.0',
        output_path
    ]

    print(f'[*] Rendering: {output_path}...')
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode == 0:
        print(f'[+] Done! Saved: {output_path}')
    else:
        print(f'[!] FFmpeg Error:\n{res.stderr[-800:]}')

render_with_music(music_v1, output_v1, music_vol=1.4, sfx_vol=0.35)
render_with_music(music_v2, output_v2, music_vol=1.4, sfx_vol=0.35)
