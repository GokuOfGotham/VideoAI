import os, subprocess

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.getenv("OUTPUT_DIR", os.path.join(PROJECT_ROOT, "output"))
MUSIC_DIR = os.getenv("EPIDEMIC_MUSIC_DIR", os.path.join(PROJECT_ROOT, "assets", "epidemic_sound"))


out_dir = OUTPUT_DIR
os.makedirs(out_dir, exist_ok=True)

video_src = r'M:\Videos\Gaming\PlayStation 5\Batman Arkham Knight\Shorts\Batman vs Squadron.mp4'
music_src = os.path.join(MUSIC_DIR, "Final_Frontier.mp3")

sfx_bone = os.path.join(MUSIC_DIR, "sfx", "Gore__Bone__Crush__Crunch.mp3")
sfx_face = os.path.join(MUSIC_DIR, "sfx", "Fight__Impact__Punch__Face.mp3")
sfx_body = os.path.join(MUSIC_DIR, "sfx", "Fight__Impact__Punch__Body.mp3")
sfx_hard = os.path.join(MUSIC_DIR, "sfx", "Fight__Impact__Punch__Hit__Hard__Variations.mp3")

out_file = os.path.join(out_dir, 'Batman_60s_Militia_Swarm_Takedown_Master.mp4')

# 60.0 continuous seconds from 30.0s to 90.0s in Batman vs Squadron.mp4
# Stage 1 (0s-12s / src 30s-42s): Initial clash & environmental throw
# Stage 2 (12s-24s / src 42s-54s): Dynamic Zoom 1.35x on electrical box slam
# Stage 3 (24s-36s / src 54s-66s): Wide multi-target cape stun & counters
# Stage 4 (36s-48s / src 66s-78s): Dynamic Zoom 1.40x on heavy gauntlet takedowns
# Stage 5 (48s-60s / src 78s-90s): Climax squad beatdown

filter_complex = f'''
[0:v]trim=start=30.0:end=42.0,setpts=PTS-STARTPTS,scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,fps=30[v0];
[0:a]atrim=start=30.0:end=42.0,asetpts=PTS-STARTPTS[a0];

[0:v]trim=start=42.0:end=54.0,setpts=PTS-STARTPTS,scale=1458:2592:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,fps=30[v1];
[0:a]atrim=start=42.0:end=54.0,asetpts=PTS-STARTPTS[a1];

[0:v]trim=start=54.0:end=66.0,setpts=PTS-STARTPTS,scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,fps=30[v2];
[0:a]atrim=start=54.0:end=66.0,asetpts=PTS-STARTPTS[a2];

[0:v]trim=start=66.0:end=78.0,setpts=PTS-STARTPTS,scale=1512:2688:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,fps=30[v3];
[0:a]atrim=start=66.0:end=78.0,asetpts=PTS-STARTPTS[a3];

[0:v]trim=start=78.0:end=90.0,setpts=PTS-STARTPTS,scale=1242:2208:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,fps=30[v4];
[0:a]atrim=start=78.0:end=90.0,asetpts=PTS-STARTPTS[a4];

[v0][a0][v1][a1][v2][a2][v3][a3][v4][a4]concat=n=5:v=1:a=1[v_raw][a_raw];

[v_raw]eq=contrast=1.16:brightness=-0.01:saturation=1.12,unsharp=5:5:1.1:5:5:0.0,format=yuv420p,fade=t=out:st=58.5:d=1.5[v_out];

[a_raw]bass=g=10:f=85:w=0.6,equalizer=f=3200:width_type=o:width=1.2:g=5.0,compand=attacks=0.01:decays=0.1:points=-80/-80|-40/-30|-20/-10|0/0:gain=3,volume=1.2[a_game_enhanced];

[1:a]volume=0.68,atrim=start=0.0:end=60.0,asetpts=PTS-STARTPTS[a_music];

[2:a]volume=1.6,adelay=13000|13000,asetpts=PTS-STARTPTS[sfx1];
[3:a]volume=1.7,adelay=23500|23500,asetpts=PTS-STARTPTS[sfx2];
[4:a]volume=1.7,adelay=37000|37000,asetpts=PTS-STARTPTS[sfx3];
[5:a]volume=1.8,adelay=49000|49000,asetpts=PTS-STARTPTS[sfx4];

[a_game_enhanced][a_music][sfx1][sfx2][sfx3][sfx4]amix=inputs=6:duration=first:dropout_transition=2:normalize=0,afade=t=out:st=58.5:d=1.5[a_out]
'''

cmd = [
    'ffmpeg', '-y',
    '-i', video_src,
    '-i', music_src,
    '-i', sfx_bone,
    '-i', sfx_face,
    '-i', sfx_body,
    '-i', sfx_hard,
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
    '-t', '60.0',
    '-movflags', '+faststart',
    out_file
]

print(f'[*] Rendering 60s Militia Swarm Combat Masterpiece: {out_file}...')
res = subprocess.run(cmd, capture_output=True, text=True)
if res.returncode == 0:
    print(f'[+] SUCCESS! Saved: {out_file} ({os.path.getsize(out_file)} bytes)')
else:
    print(f'[!] FFmpeg Error:\n{res.stderr[-800:]}')
