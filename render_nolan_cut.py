import os, subprocess

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.getenv("OUTPUT_DIR", os.path.join(PROJECT_ROOT, "output"))
MUSIC_DIR = os.getenv("EPIDEMIC_MUSIC_DIR", os.path.join(PROJECT_ROOT, "assets", "epidemic_sound"))


video_ace = os.path.join(OUTPUT_DIR, "raw_60s_ace_chemicals.mp4")
music_nolan1 = os.path.join(MUSIC_DIR, "Final_Frontier.mp3")
music_nolan2 = os.path.join(MUSIC_DIR, "Five_Minutes_Out.mp3")

out_master1 = os.path.join(OUTPUT_DIR, "Batman_60s_DarkKnight_Nolan_SingleScene_Master.mp4")
out_master2 = os.path.join(OUTPUT_DIR, "Batman_60s_DarkKnight_Brooding_SingleScene_Master.mp4")

def render_nolan_mix(video_in, music_in, video_out):
    # Professional cinematic audio balance:
    # In-game punch & combat SFX: 80%
    # Nolan / Hans Zimmer brooding orchestral score: 75%
    filter_complex = '''
    [0:v]trim=start=0.0:end=60.0,setpts=PTS-STARTPTS,fade=t=out:st=58.5:d=1.5[v_out];
    [0:a]volume=0.85,atrim=start=0.0:end=60.0,asetpts=PTS-STARTPTS[a_game];
    [1:a]volume=0.75,atrim=start=0.0:end=60.0,asetpts=PTS-STARTPTS[a_score];
    [a_game][a_score]amix=inputs=2:duration=first:dropout_transition=2:normalize=0,afade=t=out:st=58.5:d=1.5[a_out]
    '''

    cmd = [
        'ffmpeg', '-y',
        '-i', video_in,
        '-i', music_in,
        '-filter_complex', filter_complex,
        '-map', '[v_out]',
        '-map', '[a_out]',
        '-c:v', 'libx264',
        '-preset', 'fast',
        '-crf', '18',
        '-c:a', 'aac',
        '-b:a', '256k',
        '-t', '60.0',
        video_out
    ]

    print(f'[*] Rendering Nolan Dark Knight Style Short: {video_out}...')
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode == 0:
        print(f'[+] Success: {video_out}')
    else:
        print(f'[!] Error:\n{res.stderr[-800:]}')

render_nolan_mix(video_ace, music_nolan1, out_master1)
render_nolan_mix(video_ace, music_nolan2, out_master2)
