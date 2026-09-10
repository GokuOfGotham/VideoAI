import os, subprocess

out_dir = r'A:\AI\VideoAI\output'
os.makedirs(out_dir, exist_ok=True)

video_src = r'M:\Videos\Gaming\PlayStation 5\Batman Arkham Knight\Shorts\Batman Warrior.mp4'
music_src = r'A:\AI\VideoAI\assets\epidemic_sound\Final_Frontier.mp3'

sfx_bone = r'A:\AI\VideoAI\assets\epidemic_sound\sfx\Gore__Bone__Crush__Crunch.mp3'
sfx_face = r'A:\AI\VideoAI\assets\epidemic_sound\sfx\Fight__Impact__Punch__Face.mp3'
sfx_body = r'A:\AI\VideoAI\assets\epidemic_sound\sfx\Fight__Impact__Punch__Body.mp3'
sfx_hard = r'A:\AI\VideoAI\assets\epidemic_sound\sfx\Fight__Impact__Punch__Hit__Hard__Variations.mp3'

out_file = os.path.join(out_dir, 'Batman_60s_VERIFIED_COMBAT_PunchEnhanced_Master.mp4')

# 60.0 continuous seconds of verified physical combat (25.0s to 85.0s)
# Multi-stage dynamic punch-in zoom sequence:
# 0s-12s: Standard 1.0x -> Intro brawl
# 12s-22s: Zoom 1.35x -> Rapid counter beatdowns
# 22s-34s: Standard 1.0x -> Multi-enemy spin takedowns
# 34s-46s: Zoom 1.40x -> Heavy brute slams
# 46s-60s: Standard 1.1x -> Climax combo finishers

filter_complex = f'''
[0:v]trim=start=25.0:end=37.0,setpts=PTS-STARTPTS,scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,fps=30[v0];
[0:a]atrim=start=25.0:end=37.0,asetpts=PTS-STARTPTS[a0];

[0:v]trim=start=37.0:end=47.0,setpts=PTS-STARTPTS,scale=1458:2592:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,fps=30[v1];
[0:a]atrim=start=37.0:end=47.0,asetpts=PTS-STARTPTS[a1];

[0:v]trim=start=47.0:end=59.0,setpts=PTS-STARTPTS,scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,fps=30[v2];
[0:a]atrim=start=47.0:end=59.0,asetpts=PTS-STARTPTS[a2];

[0:v]trim=start=59.0:end=71.0,setpts=PTS-STARTPTS,scale=1512:2688:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,fps=30[v3];
[0:a]atrim=start=59.0:end=71.0,asetpts=PTS-STARTPTS[a3];

[0:v]trim=start=71.0:end=85.0,setpts=PTS-STARTPTS,scale=1188:2112:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,fps=30[v4];
[0:a]atrim=start=71.0:end=85.0,asetpts=PTS-STARTPTS[a4];

[v0][a0][v1][a1][v2][a2][v3][a3][v4][a4]concat=n=5:v=1:a=1[v_raw][a_raw];

[v_raw]eq=contrast=1.16:brightness=-0.01:saturation=1.12,unsharp=5:5:1.1:5:5:0.0,format=yuv420p,fade=t=out:st=58.5:d=1.5[v_out];

[a_raw]bass=g=10:f=85:w=0.6,equalizer=f=3200:width_type=o:width=1.2:g=5.0,compand=attacks=0.01:decays=0.1:points=-80/-80|-40/-30|-20/-10|0/0:gain=3,volume=1.2[a_game_enhanced];

[1:a]volume=0.65,atrim=start=0.0:end=60.0,asetpts=PTS-STARTPTS[a_music];

[2:a]volume=1.6,adelay=13500|13500,asetpts=PTS-STARTPTS[sfx1];
[3:a]volume=1.6,adelay=24000|24000,asetpts=PTS-STARTPTS[sfx2];
[4:a]volume=1.7,adelay=36000|36000,asetpts=PTS-STARTPTS[sfx3];
[5:a]volume=1.8,adelay=48500|48500,asetpts=PTS-STARTPTS[sfx4];

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

print(f'[*] Rendering Verified Combat Masterpiece: {out_file}...')
res = subprocess.run(cmd, capture_output=True, text=True)
if res.returncode == 0:
    print(f'[+] SUCCESS! Saved: {out_file} ({os.path.getsize(out_file)} bytes)')
else:
    print(f'[!] FFmpeg Error:\n{res.stderr[-800:]}')
