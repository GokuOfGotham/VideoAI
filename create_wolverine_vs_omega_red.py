"""Can Wolverine Really Beat Omega Red? — Marvel's Wolverine (PS5) vs X-Men '97.

A narrated versus essay (policy content_type `lore`: Cedar narration for the analysis,
original game / episode audio for the key scenes, an Epidemic bed under the narration)
cut from the user's 4K60 boss-fight recording of Marvel's Wolverine, the opening-chapters
recording, and two YouTube uploads of X-Men '97 S2E5. House broadcast graphics
(videoai_graphics.broadcast, Theme(subject="gaming")) rendered at 2x for the 4K main.

Stages (run in order; each is cached and idempotent):
    python create_wolverine_vs_omega_red.py narrate          # Cedar takes + word timings + ending check
    python create_wolverine_vs_omega_red.py plan             # timelines, policy + story-spine check, range audit
    python create_wolverine_vs_omega_red.py review           # director's review against the scene logs (work/scene_log/<src>)
    python create_wolverine_vs_omega_red.py music            # Epidemic bed + SFX (records the manifest)
    python create_wolverine_vs_omega_red.py render main
    python create_wolverine_vs_omega_red.py render short1|short2|short3
    python create_wolverine_vs_omega_red.py qa
    python create_wolverine_vs_omega_red.py package

Every quoted line was read off the game's own subtitles on 4K frames (work/scan/subs)
and every cut point comes from word-level transcription of the source window
(work/scan/words). See SOURCE_MANIFEST.json for every range shown.
"""
import argparse
import concurrent.futures
import json
import math
import re
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from narration_tools import load_preset  # noqa: E402
from videoai_policy import validate_script  # noqa: E402
from videoai_graphics import broadcast as bc  # noqa: E402
import recipe_tools as rt  # noqa: E402
from recipe_tools import run, FF, FP, stamp, ass_escape  # noqa: E402

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "output" / "Wolverine_vs_Omega_Red_20260915"
WORK = OUT / "work"
AUDIO = WORK / "audio"
PLATES = WORK / "plates"
SHOTS = WORK / "shots"
PREP = WORK / "prepared"
QA = WORK / "qa"
for _d in (AUDIO, PLATES, SHOTS, PREP, QA):
    _d.mkdir(parents=True, exist_ok=True)

FPS = 60
PAD_AFTER_SAY = 0.35
KINDS = ("main", "short1", "short2", "short3")
NAMES = {"main": "Can_Wolverine_Beat_Omega_Red_4K60.mp4",
         "short1": "Short_1_Omega_Means_The_End.mp4",
         "short2": "Short_2_Same_Fight_Two_Answers.mp4",
         "short3": "Short_3_Why_Omega_Red_Hates_Logan.mp4"}
TITLE = "Can Wolverine Really Beat Omega Red? Marvel's Wolverine vs X-Men '97"
SERIES = "WOLVERINE VS OMEGA RED · THE GAME VS X-MEN '97"
CHANNEL = "WHO WINS"

# --- Sources -----------------------------------------------------------------------
# speed: output seconds per file second (the Skystar upload runs at 25 fps, a PAL
# conform of 24 fps animation; it is played back at 24/25 with the pitch restored).
SOURCES = {
    "boss": dict(path=Path("M:/Videos/Gaming/Marvel's Wolverine - Wolverine vs Omega Red Boss Fight.mp4"),
                 outlet="MARVEL'S WOLVERINE", programme="Boss-fight capture (YouTube upload, watermark RUBHEN925)",
                 resolution="3840×2160 · 59.94 fps", width=3840, height=2160, fps="60000/1001", audio="AAC stereo 44.1 kHz",
                 duration=674.38, speed=1.0, kind="game", rights="User-supplied recording of a YouTube upload; game © Insomniac Games / Marvel / Sony Interactive Entertainment."),
    "intro": dict(path=Path("M:/Videos/Gaming/Marvel’s Wolverine – Brutal Intro _ Opening Scene _ 4K.webm"),
                  outlet="MARVEL'S WOLVERINE", programme="Opening-chapters capture (YouTube upload)",
                  resolution="3840×2160 · 60 fps", width=3840, height=2160, fps="60/1", audio="Opus stereo",
                  duration=1347.13, speed=1.0, kind="game", rights="User-supplied recording of a YouTube upload; game © Insomniac Games / Marvel / Sony Interactive Entertainment."),
    "x97a": dict(path=ROOT / "assets/materials/xmen97/IBRFe0c2Zls.mp4",
                 outlet="X-MEN '97", programme="S2E5 · Disney+ (YouTube: Movie Compilations, IBRFe0c2Zls)",
                 resolution="1920×1080 · 24 fps", width=1920, height=1080, fps="24/1", audio="AAC stereo 44.1 kHz",
                 duration=132.0, speed=1.0, kind="show", url="https://www.youtube.com/watch?v=IBRFe0c2Zls",
                 rights="YouTube re-upload of a Disney+ episode (standard licence, not cleared for reuse); episode © Marvel Animation / Disney. Used as short excerpts for commentary."),
    "x97b": dict(path=ROOT / "assets/materials/xmen97/3ZzXXAPWxTk.mp4",
                 outlet="X-MEN '97", programme="S2E5 · Disney+ (YouTube: Skystar Alt, 3ZzXXAPWxTk)",
                 resolution="1920×1080 · 25 fps upload, conformed to 24", width=1920, height=1080, fps="25/1", audio="AAC stereo 44.1 kHz",
                 duration=163.3, speed=25 / 24, kind="show", url="https://www.youtube.com/watch?v=3ZzXXAPWxTk",
                 rights="YouTube re-upload of a Disney+ episode (standard licence, not cleared for reuse); episode © Marvel Animation / Disney. Used as short excerpts for commentary."),
}
GAME_DATE = "PS5 · Sept 15, 2026"
SHOW_DATE = "S2E5 · July 15, 2026"


def stamp_src(t):
    t = int(round(t)); return f"{t//3600:02}:{t//60%60:02}:{t%60:02}"


# --- Editorial content ------------------------------------------------------------
# Excerpts: source, in, out (file seconds), speaker tab, quote cues [(rel_start, rel_end, text)].
# In/out points sit on word boundaries measured by whisper-1 on the source window; quotes are
# the game's own subtitle text (read on 4K frames) or the episode line confirmed by two transcribers.
EXCERPTS = {
    "omega_end": dict(src="boss", a=249.30, b=258.40, speaker="OMEGA RED", quotes=[(0.0, 2.9, "Omega, it means The End."), (3.3, 8.9, "Because I am the last thing my victims will ever see.")]),
    "essex_arkady": dict(src="boss", a=46.60, b=56.60, speaker="OMEGA RED", quotes=[(0.2, 1.6, "Essex: Arkady."), (2.5, 7.1, "I used to think you were so strong."), (8.2, 9.8, "Now look at you.")]),
    "rejected": dict(src="boss", a=79.30, b=100.30, speaker="OMEGA RED / LOGAN", quotes=[(0.2, 3.8, "Omega Red: Do you even know why your \"team\" rejected me?"), (3.9, 5.2, "Logan: Cuz you're fuckin' sick."), (6.2, 11.4, "Omega Red: At least the Reavers don't care what... or who I crave."), (12.6, 15.9, "Logan: I should'a killed you when I had the chance."), (17.4, 20.8, "Omega Red: You won't live long enough to regret it.")]),
    "still_bitter": dict(src="boss", a=164.00, b=175.00, speaker="OMEGA RED / LOGAN", quotes=[(0.1, 3.4, "Omega Red: Team X was wrong to reject me!"), (3.4, 5.3, "Logan: Still bitter, huh?"), (9.1, 10.7, "Logan: Not so tough, huh?")]),
    "die_easily": dict(src="boss", a=217.20, b=234.60, speaker="OMEGA RED / LOGAN", quotes=[(0.2, 5.7, "Omega Red: You think I would die so easily?"), (6.3, 7.9, "Omega Red: No, no, no."), (7.7, 14.6, "Omega Red: You even know why the Reavers call me Omega Red?"), (14.7, 17.0, "Logan: I don't give a shit--")]),
    "not_the_end": dict(src="boss", a=264.60, b=273.40, speaker="THE VOICE", quotes=[(0.7, 2.2, "This."), (2.2, 4.7, "Is not."), (4.7, 8.4, "The end.")]),
    "is_a_team": dict(src="boss", a=312.60, b=322.40, speaker="OMEGA RED", quotes=[(0.3, 2.9, "Now that."), (3.0, 4.2, "Wolverinetchk."), (4.4, 5.5, "That."), (5.7, 9.4, "--is a team.")]),
    "no_better": dict(src="boss", a=330.00, b=342.60, speaker="OMEGA RED", quotes=[(0.2, 4.1, "A team that's supposed to *save* mutants!"), (4.1, 7.9, "But you're no better than the rest of the world!"), (8.8, 12.3, "You turn away what you don't understand!")]),
    "hunger": dict(src="boss", a=356.60, b=366.30, speaker="OMEGA RED / LOGAN", quotes=[(0.2, 3.1, "Omega Red: The hunger never quiets!"), (5.3, 6.8, "Logan: We've all got shit!"), (7.2, 9.4, "Logan: We learn to control it!")]),
    "nothing": dict(src="boss", a=420.60, b=438.60, speaker="OMEGA RED", quotes=[(0.9, 5.4, "You! Are! NOTHING!")]),
    "russia": dict(src="boss", a=494.40, b=517.80, speaker="OMEGA RED / LOGAN", quotes=[(0.2, 3.8, "Omega Red: You knew how they treated me in Russia!"), (3.7, 7.1, "Omega Red: An outcast! No better than an animal!"), (7.1, 11.2, "Omega Red: You knew what Team X meant to me!"), (17.6, 19.8, "Omega Red: You still threw me out!"), (20.4, 23.1, "Logan: What're you waitin' for? COME ON!")]),
    "rematch": dict(src="boss", a=534.00, b=576.00, speaker="LOGAN", quotes=[(1.4, 4.6, "This the rematch you wanted?!"), (31.4, 32.6, "Where's..."), (32.6, 34.2, "...your team..."), (34.2, 35.6, "...now?!")]),
    "sample": dict(src="boss", a=581.20, b=597.60, speaker="ESSEX", quotes=[(0.6, 3.0, "Reaver: Omega Red is down!"), (5.8, 8.2, "Essex: When you are ready..."), (8.8, 11.6, "Essex: ...be a dear and grab a sample."), (12.8, 15.2, "Essex: We'll want it for the vault.")]),
    "skull": dict(src="intro", a=252.20, b=278.00, speaker="OMEGA RED", quotes=[(0.1, 1.6, "(in Russian accent) Find him."), (1.7, 7.1, "I expect one adamantium skull by sunrise."), (7.4, 10.4, "(in Russian) Understood?"), (11.3, 17.3, "Your comrades will kill any survivors at the crash site, huh?"), (17.5, 19.6, "If you fail..."), (20.7, 25.4, "*I* will ensure Team X doesn't reach the compound.")]),
    "little_wolverine": dict(src="intro", a=517.20, b=546.60, speaker="OMEGA RED / LOGAN", quotes=[(0.2, 2.5, "Omega Red: Hello, little Wolverine."), (3.5, 8.5, "Omega Red: I worked up quite an appetite chasing down your little comrade."), (10.8, 13.9, "Omega Red: I will save a little bit for after dinner."), (17.0, 21.1, "Logan: You want your rematch? Come down here and get it!"), (21.1, 29.3, "Omega Red: No, I think I prefer to watch you die scurrying around like a little rat.")]),
    "restrained": dict(src="x97a", a=3.80, b=26.20, speaker="OMEGA RED", quotes=[(0.9, 7.8, "I was restrained once, but a living weapon such as myself cannot be stopped."), (11.4, 13.8, "Not even by these insects."), (18.0, 21.6, "Wolverine's ally, you too will die.")]),
    "empire": dict(src="x97a", a=36.40, b=52.40, speaker="OMEGA RED", quotes=[(0.3, 6.4, "I was made by an empire to purify the world."), (6.4, 15.5, "Now I will kill Wolverine and unleash these creatures upon Earth to make an empire of my own.")]),
    "snikt": dict(src="x97a", a=52.40, b=58.60, speaker="ORIGINAL AUDIO", quotes=[]),
    "im_back": dict(src="x97a", a=72.60, b=77.40, speaker="WOLVERINE", quotes=[(2.0, 4.2, "I'm back, baby.")]),
    "x97_fight": dict(src="x97a", a=77.40, b=97.20, speaker="ORIGINAL AUDIO", quotes=[(5.4, 6.4, "Sabretooth: We've gotta go."), (6.5, 7.3, "It's gonna blow."), (10.8, 12.4, "Morph: Logan! Now!")]),
    "escape": dict(src="x97a", a=97.20, b=118.00, speaker="ORIGINAL AUDIO", quotes=[(5.6, 7.5, "Deathstrike: Fire it up! Fire it up!"), (7.9, 10.4, "Omega Red: No!")]),
    "not_a_monster": dict(src="x97b", a=57.30, b=76.30, speaker="MORPH", quotes=[(0.2, 1.6, "Logan, don't do this."), (2.2, 3.5, "Don't make them right about you."), (4.0, 6.5, "You're not a monster. You're my friend."), (7.3, 11.6, "When Sinister took me over, when he corrupted me, you didn't leave me behind."), (11.6, 14.5, "You came for me. Tried to bring me back."), (14.7, 18.7, "X-Men don't just cut and run. And I won't either.")]),
    "hold_him": dict(src="x97b", a=98.80, b=110.00, speaker="LADY DEATHSTRIKE", quotes=[(0.3, 3.2, "Turn it on! Hurry!"), (4.0, 7.0, "We have to... hold him!")]),
}

# Full-panel figures and lists.
EXHIBITS = {
    "first_app": bc.Exhibit("FIRST APPEARANCE", "1992", "X-MEN #4 · JIM LEE & JOHN BYRNE · ARKADY ROSSOVICH", 1.0),
    "game_length": bc.Exhibit("THE FIGHT IN MARVEL'S WOLVERINE", "7:56", "THREE ARENAS · ONE DRAIN · RECORDING 00:01:40 – 00:09:36", 1.0),
    "show_length": bc.Exhibit("THE FIGHT IN X-MEN '97", "16 SEC", "FIRST LUNGE TO OMEGA RED DOWN · ABOUT FIVE SECONDS OF BLOWS", 16 / 476),
    "kills": bc.Exhibit("TIMES WOLVERINE FINISHED HIM ON SCREEN IN 2026", "0 OF 2", "GAME: DOWN, SAMPLED · '97: LEFT IN THE FIRE", 0.0),
    "origins": bc.Exhibit("THE ONE TIME IN THE COMICS", "ORIGINS #39", "WOLVERINE: ORIGINS #39 (2009) · A BLADE MADE TO BEAT HEALING", 1.0),
}
ROWS = {
    "carbonadium": bc.Card("WHAT CARBONADIUM DOES", "", ["Soviet answer to adamantium: flexible, radioactive", "Coils that drain life energy on contact", "Slows a healing factor · poisons its owner", "One synthesizer ever built. Team X stole it"]),
    "teamx97": bc.Card("TEAM X AT WEAPON X · X-MEN '97 S2E5", "", ["Wolverine · Sabretooth · Lady Deathstrike", "Maverick · Kane · Morph", "Two of them do not leave the facility"]),
    "verdict": bc.Card("THE VERDICT", "", ["Game: Logan wins an 8-minute war, loses the drain", "X-Men '97: adamantium back, 16 seconds, done", "Both: Omega Red down, neither: Omega Red dead"]),
}

CHAPTERS = ["OMEGA MEANS THE END", "WHO IS OMEGA RED", "THE GAME'S OMEGA RED", "ROUND ONE: TRASK COMPOUND", "THE DRAIN",
            "THE RAGE", "DOWN, NOT DEAD", "X-MEN '97: SIXTEEN SECONDS", "THE VERDICT"]
CARDS = [
    bc.Card("THE QUESTION", "CAN WOLVERINE REALLY BEAT OMEGA RED?", ["Two fights this year: PS5 and X-Men '97", "Both end with Omega Red down", "Neither ends with Omega Red dead"]),
    bc.Card("THE COMICS RECORD", "ARKADY ROSSOVICH", ["X-Men #4, January 1992", "Soviet super-soldier · carbonadium coils", "Drains life to survive his own implants"]),
    bc.Card("MARVEL'S WOLVERINE", "TRASK'S MERCENARY", ["Insomniac Games · PS5 · Sept 15, 2026", "Omega Red: Raphael Corkhill · Logan: Liam McIntyre", "He beat Sabretooth before Logan arrives"]),
    bc.Card("ROUND ONE", "THE WAREHOUSE", ["Recording 00:01:40 – 00:03:15", "Coils, grabs, a health bar that barely moves", "The grievance: Team X threw him out"]),
    bc.Card("THE DRAIN", "WHERE LOGAN LOSES", ["Recording 00:03:38 – 00:04:47", "Coils go red: life-force drain", "Only the Reavers' arrival stops it"]),
    bc.Card("ROUNDS TWO AND THREE", "THE RAGE", ["Recording 00:05:24 – 00:09:36", "Crash site, then the firestorm", "\"This the rematch you wanted?!\""]),
    bc.Card("THE AFTERMATH", "DOWN, NOT DEAD", ["\"Omega Red is down!\"", "Essex wants a sample for \"the vault\"", "Comics: only Origins #39 finished him"]),
    bc.Card("X-MEN '97 S2E5", "SIXTEEN SECONDS", ["\"Weapon X, Lies, and DVDs\" · July 15, 2026", "Brood-infected Logan · adamantium restored", "Omega Red: Darin De Paul"]),
    bc.Card("THE VERDICT", "YES. HE CAN'T FINISH HIM.", ["Carbonadium doesn't care about claws", "The game makes the drain the real fight", "'97 makes adamantium the whole answer"]),
]

# Blocks per chapter: ("play", excerpt key) or ("say", chyron, narration, plan).
# plan = [(anchor phrase, shot)] where shot = ("boss"|"intro"|"x97a"|"x97b", file seconds) | ("exhibit", key) | ("rows", key).
# "" anchors the paragraph start. Seeks were chosen from inspected contact sheets (work/scan).
SECTIONS = [
    (0, [
        ("play", "omega_end"),
        ("say", "CAN WOLVERINE REALLY BEAT OMEGA RED?",
         "Omega Red, coils around Logan's throat, draining him. Can Wolverine really beat him? Yes. He did it twice this year, once on PlayStation 5 and once in X-Men '97, and both fights ended the same strange way: Omega Red on the ground, and not dead. That's the real answer, and it's more interesting than a yes or a no, because Omega Red is the one enemy who was built to outlast a healing factor, and neither version of Logan has ever found a way to finish him.",
         [("", ("boss", 258.6)), ("Yes.", ("boss", 100.5)), ("once in X-Men", ("x97a", 68.0)), ("Omega Red on the ground", ("boss", 597.6)), ("because Omega Red is the one enemy", ("boss", 125.0))]),
    ]),
    (1, [
        ("say", "ARKADY ROSSOVICH · X-MEN #4, 1992",
         "Start with who he is, because both adaptations lean on the comics. Omega Red is Arkady Rossovich, first seen in X-Men number four in January 1992, from Jim Lee and John Byrne. In the books he's a Soviet serial killer the government turned into their answer to Captain America, and the experiment gave him three things. Retractable coils in each arm, made of carbonadium. A death factor: pheromones that kill anyone standing too close. And a hunger, because the carbonadium inside him is slowly poisoning him, and the only thing that holds the poison back is draining life energy out of other people.",
         [("", ("exhibit", "first_app")), ("In the books", ("intro", 234.0)), ("Retractable coils", ("boss", 141.0)), ("A death factor", ("intro", 279.0)), ("And a hunger", ("boss", 176.0))]),
        ("say", "CARBONADIUM: THE SOVIET ADAMANTIUM",
         "Carbonadium matters. It's the Soviet attempt at adamantium: cheaper, more flexible, radioactive, and in the comics a sliver of it lodged in Logan slows his healing to a crawl. There was one machine that could make it, the carbonadium synthesizer, and Wolverine, Sabretooth and Maverick stole it on their last Team X mission. That's the original grudge. Omega Red believes Logan knows where his cure is, so every time he's thawed out, and the Soviets literally kept him in cold storage until the Hand woke him up, he comes looking for Wolverine.",
         [("", ("rows", "carbonadium")), ("There was one machine", ("boss", 148.0)), ("That's the original grudge", ("intro", 300.0))]),
    ]),
    (2, [
        ("say", "INSOMNIAC'S VERSION: TRASK'S MERCENARY",
         "Insomniac's game, out on PlayStation 5 this week, keeps the coils and the hunger and changes the grudge. Here Omega Red is a mercenary on Bolivar Trask's payroll, guarding the compound where Trask is holding Nathaniel Essex, the man who built Team X. Raphael Corkhill plays him with a purr, and the first thing he does on screen is order a Trask soldier to bring him Logan's head, then drain the messenger for practice.",
         [("", ("intro", 195.0)), ("Here Omega Red is a mercenary", ("intro", 224.5)), ("Raphael Corkhill plays him", ("intro", 242.5))]),
        ("play", "skull"),
        ("say", "SABRETOOTH ALREADY LOST TO HIM",
         "By the time Logan reaches him, Omega Red has already taken Sabretooth apart off screen. Logan's own line to Mystique is that Victor is sleeping off his fight with Omega Red. So this is a rematch on two levels: the game's own history, where Team X once turned Omega Red away, and Logan's, because he arrives at the Trask compound knowing exactly who is waiting up on that gantry.",
         [("", ("intro", 388.0)), ("Logan's own line", ("intro", 620.0)), ("So this is a rematch", ("intro", 500.0))]),
        ("play", "little_wolverine"),
    ]),
    (3, [
        ("say", "THE FIGHT STARTS WITH LOGAN LOSING",
         "The fight proper starts inside the Trask compound, in a chapter the game calls Last Meal, and it starts with Logan losing. He and Essex are airborne and nearly clear when the coils reach up, rip Logan out of the aircraft, and bring him down through the roof. Then Essex is in the coils too, and the first words Omega Red gives Logan are pity: I used to think you were so strong. Now look at you.",
         [("", ("boss", 28.5)), ("He and Essex are airborne", ("boss", 15.0)), ("when the coils reach up", ("boss", 21.0)), ("and bring him down", ("boss", 26.0)), ("Then Essex is in the coils", ("boss", 36.5))]),
        ("play", "essex_arkady"),
        ("say", "COILS, GRABS, AND A HEALTH BAR THAT BARELY MOVES",
         "Then the health bar appears and the argument starts. Insomniac writes this Omega Red as a rejected recruit: he wanted into Team X, Logan's team said no, and he has spent the years since getting stronger and getting bitter. Every taunt is about that. Mechanically, round one is about the coils. They whip at range, they grab, and when Logan gets close enough to use the claws, the bar barely moves. Watch the top of the screen: this is a boss who is designed to make the healing factor feel irrelevant.",
         [("", ("boss", 105.0)), ("Mechanically, round one", ("boss", 156.5)), ("They whip at range", ("boss", 133.0)), ("Watch the top of the screen", ("boss", 366.5))]),
        ("play", "rejected"),
        ("play", "still_bitter"),
    ]),
    (4, [
        ("say", "\"YOU THINK I WOULD DIE SO EASILY?\"",
         "Round one ends the way you'd expect, with Logan standing over him and asking what he said about regret. It's a fake-out. The coils come up from the floor, and now the game shows you what the comics have said for thirty years: the one thing a healing factor can't out-heal is a drain. The coils turn red. Logan's health drops as Omega Red's rises, and Insomniac cuts inside Logan's body to show the healing losing the race.",
         [("", ("boss", 193.0)), ("It's a fake-out", ("boss", 200.0)), ("The coils turn red", ("boss", 235.0)), ("and Insomniac cuts inside", ("boss", 242.0))]),
        ("play", "die_easily"),
        ("say", "THE DRAIN",
         "Here's the honest part of the answer. In a straight drain, Wolverine loses. There is no button for it. The speech about the last thing his victims will ever see plays over Logan being emptied out, and the only reason it stops is that Trask's Reavers arrive and call their own mercenary off. What saves Logan is the voice in his head that refuses to let it be the end, and a squad of cyborgs with orders to keep him alive.",
         [("", ("boss", 274.0)), ("In a straight drain", ("boss", 280.5)), ("and the only reason it stops", ("boss", 290.0)), ("What saves Logan", ("boss", 297.5))]),
        ("play", "not_the_end"),
        ("play", "is_a_team"),
    ]),
    (5, [
        ("say", "ROUND TWO: THE CRASH SITE",
         "Round two moves outside, to the crash site of Team X's VTOL, and the writing gets sharper. Omega Red isn't just angry at Logan, he's angry at the idea of Team X: a team that's supposed to save mutants, that turned away the one mutant who needed it most. The fight opens up too. Reavers in the arena, the coils used as tethers, and Logan finally hitting hard enough to move the bar.",
         [("", ("boss", 323.0)), ("Omega Red isn't just angry", ("boss", 343.0)), ("The fight opens up", ("boss", 378.0)), ("and Logan finally hitting", ("boss", 386.5))]),
        ("play", "no_better"),
        ("play", "hunger"),
        ("say", "\"YOU! ARE! NOTHING!\"",
         "The turn comes when Omega Red stops talking. He powers up, the coils go red again, and he leaps from the wreck with the three words that end the second round and blow the arena apart.",
         [("", ("boss", 397.0)), ("He powers up", ("boss", 401.5)), ("and he leaps", ("boss", 406.0))]),
        ("play", "nothing"),
        ("say", "ROUND THREE: THE FIRESTORM",
         "Round three is the firestorm, and it's the best stretch of the fight: Omega Red shouting at his own Reavers not to interfere, Logan bleeding through every animation, and the last speech, which is the game's whole thesis on the character. He was an outcast in Russia. Team X was the first thing that ever looked like belonging. And Team X threw him out.",
         [("", ("boss", 440.0)), ("Omega Red shouting", ("boss", 473.0)), ("Logan bleeding", ("boss", 478.5)), ("He was an outcast", ("boss", 449.0))]),
        ("play", "russia"),
        ("say", "\"THIS THE REMATCH YOU WANTED?!\"",
         "And then Logan takes the coil away from him. The finisher is a grapple, not a slash: Wolverine wraps the carbonadium around its owner and drives him into the dirt, and the last line of the fight isn't a joke. It's the same wound Omega Red has been talking about for eight minutes, handed back.",
         [("", ("boss", 484.6)), ("The finisher is a grapple", ("boss", 518.5))]),
        ("play", "rematch"),
    ]),
    (6, [
        ("say", "\"OMEGA RED IS DOWN!\" NOT \"DEAD\"",
         "Listen to the word the Reaver uses. Down. Not dead. Omega Red is lying in the fire with his coils spent, and the game does not let Logan finish him. Instead Essex, the man Team X just rescued, walks over with the creepiest line in the chapter: grab a sample, we'll want it for the vault. That's the game telling you Omega Red is an asset, not a corpse, and that whatever Essex is building, carbonadium and a man who drains mutants are on the shopping list.",
         [("", ("boss", 576.2)), ("Omega Red is lying in the fire", ("boss", 605.0)), ("Instead Essex", ("boss", 612.0)), ("That's the game telling you", ("boss", 621.5))]),
        ("play", "sample"),
        ("say", "THE COMICS PRECEDENT",
         "The comics back the game up. Across three decades Wolverine has beaten Omega Red again and again, and he has finished him exactly once, in Wolverine: Origins number thirty-nine in 2009, and only with a blade forged specifically to beat healing factors. Claws alone have never done it. Insomniac knows that, so they stage the drain as the real fight and treat the finisher as a reprieve.",
         [("", ("exhibit", "origins")), ("Claws alone have never done it", ("boss", 632.0)), ("so they stage the drain", ("boss", 636.0))]),
    ]),
    (7, [
        ("say", "X-MEN '97, SEASON TWO, EPISODE FIVE",
         "Now the other answer. X-Men '97, season two, episode five, Weapon X, Lies, and DVDs, released July fifteenth. Logan takes a Team X reunion into the old Weapon X facility: Sabretooth, Lady Deathstrike, Maverick, Kane, and Morph flying the jet. The place is crawling with the Brood, and the Brood want Wolverine because his body can survive what kills them. They get him. Halfway through the episode Logan is a Brood, and it takes Morph talking him down and Deathstrike and Sabretooth dragging him into an adamantium tank to get him back.",
         [("", ("x97b", 8.0)), ("Sabretooth, Lady Deathstrike", ("rows", "teamx97")), ("The place is crawling", ("x97b", 28.0)), ("They get him", ("x97b", 35.0)), ("and it takes Morph", ("x97b", 44.0))]),
        ("play", "not_a_monster"),
        ("play", "hold_him"),
        ("say", "OMEGA RED WAKES UP",
         "Omega Red is the complication. He's been on ice at Weapon X since the original series, and the chaos wakes him. Darin De Paul plays him as a Cold War relic who has found a new army in the Brood, and his plan is the comics' plan with a twist: kill Wolverine, then use the aliens to build an empire of his own.",
         [("", ("x97b", 128.0)), ("Darin De Paul plays him", ("x97a", 26.6)), ("and his plan is the comics' plan", ("x97b", 136.0))]),
        ("play", "restrained"),
        ("play", "empire"),
        ("say", "ADAMANTIUM RESTORED",
         "And here's the difference. In the game, Logan beats Omega Red with what he walked in with. In '97, he beats him with what he just got back. The tank works. The claws that come through the glass are adamantium, and the show has no interest in a long fight after that. Omega Red is a proof of concept.",
         [("", ("x97a", 58.7)), ("The tank works", ("x97b", 110.0)), ("and the show has no interest", ("x97b", 143.0))]),
        ("play", "snikt"),
        ("play", "im_back"),
        ("say", "SIXTEEN SECONDS",
         "From Wolverine's first lunge to Omega Red hitting the floor is sixteen seconds of screen time, and about five of those are Logan actually hitting him. One whip lands. Logan takes it, closes, cuts through the coil, and puts him down while the facility starts to go. Then they leave him there, in the fire, and the building comes down on top of him.",
         [("", ("exhibit", "show_length")), ("One whip lands", ("x97b", 148.4)), ("Then they leave him there", ("x97a", 118.5))]),
        ("play", "x97_fight"),
        ("play", "escape"),
    ]),
    (8, [
        ("say", "SAME FIGHT, TWO ANSWERS",
         "So, same enemy, same year, two answers. The game says Wolverine can beat Omega Red in a war, as long as he never lets the coils settle, and it makes the drain the one part of the fight that Logan cannot win alone. X-Men '97 says the whole question is adamantium: without it, Logan is a Brood in a tank; with it, Omega Red lasts sixteen seconds. Neither version kills him. The game bags him for Essex. The show buries him and doesn't look back, which in this franchise is how you keep a villain.",
         [("", ("exhibit", "game_length")), ("as long as he never lets the coils settle", ("boss", 464.5)), ("X-Men '97 says", ("x97b", 76.5)), ("Neither version kills him", ("exhibit", "kills")), ("The show buries him", ("x97a", 125.5))]),
        ("say", "YES. AND HE CAN'T FINISH HIM.",
         "So can Wolverine really beat Omega Red? Yes. Both times, on screen, this year. Can he finish him? Not with claws. Carbonadium doesn't care about adamantium, and a drain doesn't care about a healing factor, so the story always leaves the one man who can empty Logan out alive. That's why Essex wants a sample, and it's worth watching what he does with it.",
         [("", ("rows", "verdict")), ("Can he finish him", ("boss", 643.0)), ("That's why Essex wants a sample", ("boss", 655.0))]),
    ]),
]

# --- Shorts (standalone; each reuses main-video ranges but never repeats a range within itself) ---
SHORTS = {
    "short1": dict(
        title="Omega Red's Drain Is the One Thing Wolverine Can't Heal", series="OMEGA MEANS THE END · MARVEL'S WOLVERINE",
        chapters=["OMEGA MEANS THE END", "THE DRAIN", "DOWN, NOT DEAD"],
        cards=[bc.Card("MARVEL'S WOLVERINE · PS5", "OMEGA MEANS THE END", ["\"The last thing my victims will ever see\"", "Carbonadium coils drain life energy", "The one fight Logan can't heal through"]),
               bc.Card("THE DRAIN", "WHERE LOGAN LOSES", ["Coils go red: his health drains, Omega Red's rises", "No button beats it", "Trask's Reavers call him off"]),
               bc.Card("THE ANSWER", "DOWN, NOT DEAD", ["Logan wins the rematch minutes later", "Omega Red is \"down\" — Essex wants a sample", "Comics: finished once, Origins #39"])],
        blocks=[("play", "omega_end"),
                ("say", 1, "That's Omega Red draining Wolverine in Marvel's Wolverine, the one attack Logan can't heal through. His coils are carbonadium, the Soviet knock-off of adamantium, and wrapped around him they pull life out faster than it comes back. Watch the bars: his drops, Omega Red's rises. Only Trask's Reavers calling their mercenary off stops it.",
                 [("", ("boss", 235.0)), ("His coils are carbonadium", ("boss", 141.0)), ("Watch the bars", ("boss", 242.0)), ("Only Trask's Reavers", ("boss", 290.0))]),
                ("play", "not_the_end"),
                ("say", 2, "Logan wins the rematch minutes later. But the Reaver's word is down, not dead, and Essex asks for a sample. In thirty years of comics Wolverine has finished Omega Red once, and never with claws.",
                 [("", ("boss", 576.5)), ("and Essex asks for a sample", ("boss", 598.0)), ("In thirty years", ("boss", 625.0))])]),
    "short2": dict(
        title="Wolverine vs Omega Red: The Game vs X-Men '97", series="SAME FIGHT, TWO ANSWERS",
        chapters=["MARVEL'S WOLVERINE", "X-MEN '97", "WHO DID IT BETTER?"],
        cards=[bc.Card("MARVEL'S WOLVERINE · PS5", "AN 8-MINUTE WAR", ["Three arenas, one drain Logan can't heal", "Finisher: the coil turned on its owner", "\"Where's your team now?!\""]),
               bc.Card("X-MEN '97 · S2E5", "SIXTEEN SECONDS", ["Adamantium restored in the Weapon X tank", "One whip lands, then five seconds of blows", "Left in the fire as the facility blows"]),
               bc.Card("THE VERDICT", "YES. HE CAN'T FINISH HIM.", ["Both: Omega Red down", "Neither: Omega Red dead", "Carbonadium doesn't care about claws"])],
        blocks=[("say", 0, "Wolverine fought Omega Red twice this year. In Marvel's Wolverine it's an eight-minute war across three arenas, with a drain Logan can't heal through, and it ends with the carbonadium coil wrapped around its owner.",
                 [("", ("boss", 104.5)), ("with a drain", ("boss", 235.0)), ("and it ends with", ("boss", 523.2))]),
                ("play", "rematch_short"),
                ("say", 1, "In X-Men '97, Logan comes out of the Weapon X tank with his adamantium back, and Omega Red lasts sixteen seconds.",
                 [("", ("x97a", 52.4)), ("and Omega Red lasts", ("x97b", 156.5))]),
                ("play", "x97_fight_short"),
                ("say", 2, "The game makes the drain the real fight. The show makes adamantium the whole answer. Both leave Omega Red down. Neither kills him, because carbonadium doesn't care about claws.",
                 [("", ("boss", 603.0)), ("Both leave Omega Red down", ("x97a", 118.5)), ("because carbonadium", ("boss", 625.0))])]),
    "short3": dict(
        title="Why Omega Red Hates Wolverine (Game vs Comics)", series="WHY OMEGA RED HATES LOGAN",
        chapters=["\"WHY YOUR TEAM REJECTED ME\"", "TWO GRUDGES", "THE REMATCH"],
        cards=[bc.Card("MARVEL'S WOLVERINE · PS5", "TEAM X THREW HIM OUT", ["He wanted in. Logan's team said no", "\"Cuz you're fuckin' sick\"", "Years of getting stronger, and bitter"]),
               bc.Card("GAME VS COMICS", "TWO GRUDGES, ONE TARGET", ["Game: Team X threw him out", "Comics: Team X stole his cure, the synthesizer", "Either way, the man who drains mutants hunts Logan"]),
               bc.Card("THE REMATCH", "\"YOU STILL THREW ME OUT!\"", ["An outcast in Russia", "Team X was the first thing like belonging", "Logan hands the wound back"])],
        blocks=[("play", "rejected_short"),
                ("say", 1, "That's the grudge in Marvel's Wolverine: Omega Red wanted into Team X, Logan's team said no, and he's spent the years since getting stronger and bitter. The comics give a different reason: his carbonadium coils are poisoning him, one machine makes the cure, and Wolverine, Sabretooth and Maverick stole it.",
                 [("", ("boss", 104.5)), ("The comics give", ("boss", 141.0)), ("and Wolverine, Sabretooth", ("boss", 148.0))]),
                ("play", "russia_short"),
                ("say", 2, "Logan's answer is the finisher, and the same wound handed back: where's your team now?",
                 [("", ("boss", 523.2)), ("where's your team now", ("boss", 565.4))])]),
}
# Short-only excerpt trims (subsets of the main excerpts, still on word boundaries).
EXCERPTS.update({
    "rematch_short": dict(src="boss", a=534.00, b=544.00, speaker="LOGAN", quotes=[(1.4, 4.6, "This the rematch you wanted?!")]),
    "x97_fight_short": dict(src="x97a", a=87.00, b=97.20, speaker="ORIGINAL AUDIO", quotes=[(1.2, 2.8, "Morph: Logan! Now!")]),
    "rejected_short": dict(src="boss", a=79.30, b=90.80, speaker="OMEGA RED / LOGAN", quotes=[(0.2, 3.8, "Omega Red: Do you even know why your \"team\" rejected me?"), (3.9, 5.2, "Logan: Cuz you're fuckin' sick."), (6.2, 11.4, "Omega Red: At least the Reavers don't care what... or who I crave.")]),
    "russia_short": dict(src="boss", a=502.80, b=517.80, speaker="OMEGA RED / LOGAN", quotes=[(0.1, 2.9, "Omega Red: You knew what Team X meant to me!"), (9.2, 11.4, "Omega Red: You still threw me out!"), (12.0, 14.7, "Logan: What're you waitin' for? COME ON!")]),
})

# Story spine (videoai_director.story). Each beat is placed at a narration anchor (unit, phrase) or at an excerpt's start;
# plan() resolves the times from the recorded takes so the spine follows the cut, not an estimate.
SPINE_BEATS = [
    ("hook", ("play", "omega_end"), "Omega Red's own line with original audio while the red coils drain Logan"),
    ("claim", ("main_00_01", "Yes."), "Yes: he beat him twice this year, and neither time was Omega Red dead"),
    ("evidence", ("main_01_00", ""), "X-Men #4 (1992), the coils, the death factor, the hunger"),
    ("evidence", ("play", "skull"), "Skull by sunrise: the game's Omega Red orders Logan's head and drains the messenger"),
    ("question", ("main_02_02", ""), "Sabretooth already lost to him, so this is a rematch on two levels"),
    ("evidence", ("play", "rejected"), "'Do you even know why your team rejected me?'"),
    ("evidence", ("play", "still_bitter"), "'Team X was wrong to reject me!'"),
    ("rehook", ("main_04_00", "It's a fake-out"), "Round one's win is a fake-out: the coils come up from the floor"),
    ("turn", ("main_04_02", "In a straight drain"), "In a straight drain, Wolverine loses; only the Reavers stop it"),
    ("evidence", ("play", "not_the_end"), "'This. Is not. The end.'"),
    ("rehook", ("main_05_00", ""), "Round two moves outside and the writing gets sharper"),
    ("evidence", ("play", "no_better"), "'You turn away what you don't understand!'"),
    ("rehook", ("main_05_03", ""), "The turn comes when Omega Red stops talking"),
    ("evidence", ("play", "nothing"), "'You! Are! NOTHING!'"),
    ("evidence", ("play", "russia"), "'You knew what Team X meant to me!'"),
    ("evidence", ("play", "rematch"), "'This the rematch you wanted?!' — the finisher"),
    ("open_loop", ("play", "sample"), "Essex wants a sample for the vault", "sample"),
    ("evidence", ("main_06_02", ""), "Wolverine: Origins #39, the one time"),
    ("rehook", ("main_07_00", ""), "Now the other answer: X-Men '97"),
    ("evidence", ("play", "not_a_monster"), "Morph: 'You're not a monster'; the tank"),
    ("evidence", ("play", "empire"), "'I was made by an empire to purify the world'"),
    ("rehook", ("main_07_06", ""), "Here's the difference: what Logan walked in with versus what he just got back"),
    ("evidence", ("main_07_09", ""), "Sixteen seconds, measured at 2 fps"),
    ("payoff", ("main_08_00", ""), "Same fight, two answers: Wolverine beats Omega Red both times; neither kills him"),
    ("close_loop", ("main_08_01", "That's why Essex wants a sample"), "That's why Essex wants a sample", "sample"),
    ("button", ("main_08_01", "and it's worth watching"), "and it's worth watching what he does with it"),
]
CHAPTER_KINDS = ["claim", "question", "other", "other", "claim", "other", "claim", "claim", "other"]


def story_spine(data):
    """Resolve SPINE_BEATS against a built timeline (words carry unit names; shots carry excerpt keys)."""
    words_by_unit = {}
    for w in data["words"]:
        words_by_unit.setdefault(w["unit"], []).append(w)
    beats = []
    for role, where, text, *loop in SPINE_BEATS:
        if where[0] == "play":
            at = next(s["start"] for s in data["shots"] if s.get("excerpt") == where[1])
        else:
            unit, phrase = where; ws = words_by_unit[unit]
            at = ws[0]["start"] if not phrase else rt.anchor_time(ws, phrase)
        beat = {"role": role, "at": round(at, 1), "text": text}
        if loop:
            beat["loop_id"] = loop[0]
        beats.append(beat)
    # Every excerpt and every exhibit is evidence by construction; declare the ones the list above did not name.
    named = {round(b["at"], 1) for b in beats}
    for sh in data["shots"]:
        if (sh.get("excerpt") or sh.get("exhibit") or sh.get("rows")) and round(sh["start"], 1) not in named:
            what = sh.get("excerpt") or sh.get("exhibit") or sh.get("rows")
            beats.append({"role": "evidence", "at": round(sh["start"], 1), "text": f"{'excerpt' if sh.get('excerpt') else 'graphic'}: {what}"})
    beats.sort(key=lambda b: b["at"])
    chapters = [{"title": c, "start": round(sec["start"], 1), "kind": k} for c, sec, k in zip(CHAPTERS, data["sections"], CHAPTER_KINDS)]
    return {"title_question": "Can Wolverine really beat Omega Red?",
            "thesis": "Yes, twice on screen this year, and neither version of Logan can finish him, because carbonadium does not care about claws.",
            "beats": beats, "chapters": chapters}


REVIEW = {
    "main": {
        "content_type": "lore", "format": "long", "hook_start_seconds": 0,
        "hook": "Second zero: Omega Red's own line from the recording (00:04:09) with original audio — 'Omega, it means The End. Because I am the last thing my victims will ever see.' — while his red carbonadium coils drain Logan.",
        "first_payoff_seconds": 14,
        "first_payoff": "At about fourteen seconds the narration answers the title: yes, he beat him twice this year (PS5 and X-Men '97), and both fights ended with Omega Red down and not dead — the thesis the rest of the video argues.",
        "pacing_review": "Format: narrated versus essay (lore) with the game's and the episode's own audio carrying the key scenes. Viewer question: can Wolverine really beat Omega Red, and why do both 2026 versions stop short of killing him? Evidence: the user's 4K60 boss-fight recording (every line read off the game's subtitles on 4K frames; fight structure — warehouse 1:40–3:15, drain 3:38–4:47, crash site 5:24–7:05, firestorm 7:20–9:36 — from contact sheets), the opening-chapters recording (Omega Red's introduction 4:04–4:38, 'Hello, little Wolverine' 8:37–9:07), and X-Men '97 S2E5 clips (Brood-Logan, the tank, Omega Red waking, the 16-second fight measured at 2 fps). Comics facts checked against Wikipedia (FACT_CHECK.md). Cuts: the game's repeated whip cycles, menus and the Reavers' crowd-control sections are not shown; the excerpts are complete lines cut on measured word boundaries. Chapters come from the final narration timing.",
        "audio_mode": "cedar", "standalone": True, "overrides": {},
    },
    "short1": {"content_type": "lore", "format": "short", "hook_start_seconds": 0,
               "hook": "Second zero: Omega Red's 'Omega, it means The End' line with original audio while the red coils drain Logan (recording 00:04:09).",
               "first_payoff_seconds": 10, "first_payoff": "By ten seconds the narration names it: the one attack in the game Logan cannot heal through, and why (carbonadium).",
               "pacing_review": "One complete insight: the drain beats the healing factor; Logan wins the rematch but Omega Red is 'down', not dead. Ends within a second of the last word; no reference to the main video.",
               "audio_mode": "cedar", "standalone": True, "overrides": {}},
    "short2": {"content_type": "lore", "format": "short", "hook_start_seconds": 0,
               "hook": "Second zero: 'Wolverine fought Omega Red twice this year' over the game's opening exchange (recording 00:01:46).",
               "first_payoff_seconds": 8, "first_payoff": "By eight seconds: the game's fight is an eight-minute war with a drain Logan can't heal; the contrast (16 seconds in '97) follows immediately.",
               "pacing_review": "One complete comparison with both finishers shown (game 8:54–9:08, show 1:26–1:37). Ends within a second of the last word; no reference to the main video.",
               "audio_mode": "cedar", "standalone": True, "overrides": {}},
    "short3": {"content_type": "lore", "format": "short", "hook_start_seconds": 0,
               "hook": "Second zero: 'Do you even know why your team rejected me?' / 'Cuz you're fuckin' sick' with original audio (recording 00:01:19).",
               "first_payoff_seconds": 12, "first_payoff": "By twelve seconds the narration states the game's grudge (Team X threw him out) and immediately contrasts the comics' (the stolen carbonadium synthesizer).",
               "pacing_review": "One complete insight: two different reasons for the same grudge, closed by the finisher line. Ends within a second of the last word; no reference to the main video.",
               "audio_mode": "cedar", "standalone": True, "overrides": {}},
}


# --- Narration ---------------------------------------------------------------------
def narration_units(kind):
    units = []
    if kind == "main":
        for i, (sec, blocks) in enumerate(SECTIONS):
            for j, b in enumerate(blocks):
                if b[0] == "say":
                    units.append((f"main_{i:02}_{j:02}", b[2]))
    else:
        for j, b in enumerate(SHORTS[kind]["blocks"]):
            if b[0] == "say":
                units.append((f"{kind}_{j:02}", b[2]))
    return units


def take(name):
    meta = AUDIO / (name + ".tight.json")
    if meta.exists():
        return json.loads(meta.read_text(encoding="utf-8"))
    raise RuntimeError(f"Run `narrate` first: {name}")


def stage_narrate():
    preset = load_preset()
    units = [u for k in KINDS for u in narration_units(k)]

    def one(unit):
        name, text = unit
        r = rt.take_report(name, text, AUDIO, preset)
        flag = "" if r["ending_ok"] else "   <-- ENDING NOT HEARD"
        print(f"{name:<14} {r['seconds']:6.2f}s  (-{r['removed_seconds']:.2f}s silence)  agreement {r['agreement']:.3f}  diffs {len(r['differences'])}{flag}", flush=True)
        return r
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        reports = list(pool.map(one, units))
    (WORK / "narration_report.json").write_text(json.dumps([{k: v for k, v in r.items() if k != "words"} for r in reports], indent=1, ensure_ascii=False), encoding="utf-8")
    for kind in KINDS:
        names = {n for n, _ in narration_units(kind)}
        print(f"{kind}: narration {sum(r['seconds'] for r in reports if r['name'] in names):.1f}s")
    bad = [r["name"] for r in reports if not r["ending_ok"]]
    if bad:
        print("Endings not confirmed by either transcriber:", bad, "— rewrite the ending as a full sentence and delete that take to re-record.")


# --- Timeline -----------------------------------------------------------------------
def excerpt_duration(key):
    e = EXCERPTS[key]; return (e["b"] - e["a"]) * SOURCES[e["src"]]["speed"]


def build_timeline(kind):
    """Shots, voice track and word timings for one export."""
    offset = 0
    shots, parts, words, sections, quotes = [], [], [], [], []

    def add_voice(path, frames):
        dest = PREP / f"{kind}_voice_{len(parts):03}.wav"
        if path is None:
            run([FF, "-v", "error", "-y", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-t", frames / FPS, "-c:a", "pcm_s16le", dest])
        else:
            run([FF, "-v", "error", "-y", "-i", path, "-vn", "-af", "aresample=48000,asetpts=N/SR/TB,apad", "-t", frames / FPS, "-ar", 48000, "-ac", 2, "-c:a", "pcm_s16le", dest])
        parts.append(dest)

    def add_play(key, section, card):
        nonlocal offset
        e = EXCERPTS[key]; frames = round(excerpt_duration(key) * FPS)
        add_voice(None, frames)
        shots.append(dict(start=offset / FPS, duration=frames / FPS, frames=frames, section=section, card=card, src=e["src"], seek=e["a"],
                          seek_end=e["b"], sound=True, speaker=e["speaker"], excerpt=key, exhibit=None, rows=None, chyron=None, anchor=key, unit=None))
        for qa, qb, text in e["quotes"]:
            quotes.append((offset / FPS + qa * SOURCES[e["src"]]["speed"], offset / FPS + min(qb, e["b"] - e["a"]) * SOURCES[e["src"]]["speed"], text))
        offset += frames

    def add_say(name, text, plan, section, chyron, card):
        nonlocal offset
        t = take(name); local = rt.script_words(t["words"], text); frames = math.ceil((t["seconds"] + PAD_AFTER_SAY) * FPS)
        add_voice(AUDIO / (name + ".tight.wav"), frames)
        env, step = rt.speech_envelope(AUDIO / (name + ".tight.wav")); local = rt.retime_words(local, env, step)
        words.extend(dict(w, start=round(w["start"] + offset / FPS, 3), end=round(w["end"] + offset / FPS, 3), unit=name) for w in local)
        times = [round(rt.anchor_time(local, p[0]) * FPS) for p in plan] + [frames]
        for p, fa, fb in zip(plan, times, times[1:]):
            if fb <= fa:
                raise ValueError(f"Bad cut order in {name}: {p[0]!r}")
            kind_, ref = p[1]
            dur = (fb - fa) / FPS
            if kind_ in ("exhibit", "rows"):
                shots.append(dict(start=(offset + fa) / FPS, duration=dur, frames=fb - fa, section=section, card=card, src=None, seek=None, seek_end=None,
                                  sound=False, speaker=None, excerpt=None, exhibit=ref if kind_ == "exhibit" else None, rows=ref if kind_ == "rows" else None,
                                  chyron=chyron, anchor=p[0], unit=name))
            else:
                span = dur / SOURCES[kind_]["speed"]
                shots.append(dict(start=(offset + fa) / FPS, duration=dur, frames=fb - fa, section=section, card=card, src=kind_, seek=float(ref), seek_end=round(float(ref) + span, 3),
                                  sound=False, speaker=None, excerpt=None, exhibit=None, rows=None, chyron=chyron, anchor=p[0], unit=name))
        offset += frames

    if kind == "main":
        for i, (sec, blocks) in enumerate(SECTIONS):
            sections.append(dict(index=i, start=offset / FPS, chapter=CHAPTERS[i]))
            for j, b in enumerate(blocks):
                if b[0] == "play":
                    add_play(b[1], i, i)
                else:
                    add_say(f"main_{i:02}_{j:02}", b[2], b[3], i, b[1], i)
    else:
        spec = SHORTS[kind]
        for i, c in enumerate(spec["chapters"]):
            sections.append(dict(index=i, start=None, chapter=c))
        cur = 0
        for j, b in enumerate(spec["blocks"]):
            if b[0] == "play":
                add_play(b[1], cur, cur)
            else:
                cur = b[1]
                add_say(f"{kind}_{j:02}", b[2], b[3], cur, None, cur)
        for s in sections:
            s["start"] = next((x["start"] for x in shots if x["section"] == s["index"]), 0.0)
        tail = math.ceil(0.6 * FPS) - math.ceil(PAD_AFTER_SAY * FPS)
        last = shots[-1]; last["frames"] += tail; last["duration"] = last["frames"] / FPS
        if last["seek"] is not None:
            last["seek_end"] = round(last["seek"] + last["duration"] / SOURCES[last["src"]]["speed"], 3)
        offset += tail
        if offset / FPS > 60:
            raise ValueError(f"{kind} runs {offset/FPS:.1f}s; rewrite to fit 60 s")
    for k, s in enumerate(shots):
        s["index"] = k
    listing = PREP / f"{kind}_voice.txt"
    listing.write_text("\n".join("file '" + p.as_posix() + "'" for p in parts), encoding="utf-8")
    master = OUT / f"{kind}_voice_master_48k24.wav"
    run([FF, "-v", "error", "-y", "-f", "concat", "-safe", 0, "-i", listing, "-af", "aresample=48000,asetpts=N/SR/TB,apad", "-t", offset / FPS, "-ar", 48000, "-ac", 2, "-c:a", "pcm_s24le", master])
    data = dict(duration=offset / FPS, frames=offset, words=words, shots=shots, sections=sections, quotes=quotes)
    (WORK / f"{kind}_timeline.json").write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    return data


def audit_ranges(timelines):
    """No source range is shown twice within an export (the Shorts may reuse main ranges)."""
    used, problems = [], []
    for kind, data in timelines.items():
        for s in data["shots"]:
            if s["src"] is not None:
                used.append((kind, s["src"], s["index"], s["seek"], s["seek_end"], s["anchor"]))
    for i, a in enumerate(used):
        for b in used[i + 1:]:
            if a[0] == b[0] and a[1] == b[1] and a[3] < b[4] - 0.05 and b[3] < a[4] - 0.05:
                problems.append((a, b))
    return used, problems


def stage_plan():
    timelines = {k: build_timeline(k) for k in KINDS}
    used, problems = audit_ranges(timelines)
    for p in problems:
        print("RANGE OVERLAP:", p)
    for kind, data in timelines.items():
        review = dict(REVIEW[kind])
        plan = {"title": TITLE if kind == "main" else SHORTS[kind]["title"], "production_review": review,
                "narration_script": " ".join(t for _, t in narration_units(kind)), "duration": data["duration"],
                "sources": {k: {"file": str(v["path"]), **{kk: vv for kk, vv in v.items() if kk != "path"}} for k, v in SOURCES.items()},
                "used_ranges": [{"export": kind, "source": s["src"], "source_in": s["seek"], "source_out": s["seek_end"], "edit_start": s["start"], "edit_duration": s["duration"],
                                 "original_audio": s["sound"], "speaker": s["speaker"], "anchor": s["anchor"]} for s in data["shots"] if s["src"] is not None],
                "shots": [{"role": "content", "start": s["start"], "duration": s["duration"], "source": s["src"] or "graphic", "sound": s["sound"]} for s in data["shots"]]}
        if kind == "main":
            plan["story_spine"] = story_spine(data)
        plan["production_policy_check"] = validate_script(plan, duration=data["duration"])
        (OUT / f"{kind}_production_plan.json").write_text(json.dumps(plan, indent=1, ensure_ascii=False), encoding="utf-8")
        story_result = plan["production_policy_check"].get("story")
        if story_result:
            for w in story_result.get("warnings", []):
                print(f"   story warning: {w}")
        foot = sum(s["duration"] for s in data["shots"] if s["src"] is not None); orig = sum(s["duration"] for s in data["shots"] if s["sound"])
        print(f"{kind}: {data['duration']:.1f}s ({int(data['duration']//60)}:{int(data['duration']%60):02d}), {len(data['shots'])} shots, footage {foot:.0f}s, original audio {orig:.0f}s, policy {plan['production_policy_check']['status']}")
        for sec in data["sections"]:
            print(f"   {int(sec['start']//60)}:{int(sec['start']%60):02d} {sec['chapter']}")
    if problems:
        raise SystemExit(f"{len(problems)} overlapping source ranges; adjust seeks.")
    print(f"{len(used)} source ranges, none reused within an export.")


def stage_review():
    """Director's review of the main cut against the boss recording's scene log (python director_tool.py index …)."""
    from videoai_director import review, scene_index
    plan = json.loads((OUT / "main_production_plan.json").read_text(encoding="utf-8")); data = json.loads((WORK / "main_timeline.json").read_text(encoding="utf-8"))
    logs = {}
    for key in SOURCES:
        p = WORK / "scene_log" / key / "scene_log.json"
        if p.exists():
            logs[key] = scene_index.load(p)
    texts = {name: text for k in KINDS for name, text in narration_units(k)}
    result = review.director_review(plan, data, logs, unit_texts=texts)
    (OUT / "DIRECTOR_REVIEW.md").write_text(review.markdown(result, f"Director review — {TITLE}"), encoding="utf-8")
    (OUT / "DIRECTOR_REVIEW.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print(review.markdown(result, f"Director review — {TITLE}"))


# --- Plates and shots ---------------------------------------------------------------
def house_theme(kind):
    if kind == "main":
        return bc.Theme(subject="gaming", channel=CHANNEL, series=SERIES, chapters=CHAPTERS,
                        strap_left="WHAT THE FOOTAGE SHOWS  /  THE COMICS RECORD  /  OPINION",
                        strap_right="MARVEL'S WOLVERINE (PS5) · X-MEN '97 S2E5 · AI NARRATION", muted_label="UNDER NARRATION", graphic_label="GRAPHIC")
    spec = SHORTS[kind]
    return bc.Theme(subject="gaming", channel=CHANNEL, series=spec["series"], chapters=spec["chapters"],
                    strap_left="MARVEL'S WOLVERINE (PS5) · X-MEN '97 S2E5 · AI NARRATION", muted_label="UNDER NARRATION", graphic_label="GRAPHIC")


def source_for(s):
    meta = SOURCES[s["src"]]
    date = ("Recording " if meta["kind"] == "game" else "Clip ") + stamp_src(s["seek"])
    programme = (GAME_DATE if meta["kind"] == "game" else SHOW_DATE)
    return bc.Source(meta["outlet"], programme, date, meta["resolution"])


def house_shot(kind, s):
    vert = kind != "main"
    card = CARDS[s["card"]] if kind == "main" else SHORTS[kind]["cards"][s["card"]]
    src = source_for(s) if s["src"] is not None else None
    ex = EXHIBITS[s["exhibit"]] if s["exhibit"] else None
    rows_card = ROWS[s["rows"]] if s["rows"] else None
    shot = bc.Shot(kind="short" if vert else "main", section=s["section"], card=card if not rows_card else bc.Card(rows_card.kicker, card.big, card.bullets),
                   source=src, sound=s["sound"], speaker=s["speaker"], chyron=s["chyron"], exhibit=ex, rows=rows_card.bullets if rows_card else ())
    return shot


def encoder_args(final=False, vert=False):
    if rt.nvenc_available():
        if final:
            return ["-c:v", "h264_nvenc", "-preset", "p6", "-rc", "vbr", "-cq", 18 if vert else 19, "-b:v", "12M" if vert else "45M", "-maxrate", "20M" if vert else "70M", "-bufsize", "30M" if vert else "100M", "-profile:v", "high"]
        return ["-c:v", "h264_nvenc", "-preset", "p5", "-rc", "vbr", "-cq", 18, "-b:v", 0, "-maxrate", "80M", "-bufsize", "120M", "-profile:v", "high"]
    return ["-c:v", "libx264", "-preset", "medium", "-crf", 18]


def render_shot(kind, s):
    vert = kind != "main"; scale = 1 if vert else 2
    platepath, (x, y, sw, sh) = bc.render_plate(house_theme(kind), house_shot(kind, s), PLATES / f"{kind}_{s['index']:03}.png", scale=scale)
    dest = SHOTS / f"{kind}_{s['index']:03}.mp4"; aud = dest.with_suffix(".wav")
    key = json.dumps({k: s[k] for k in ("src", "seek", "frames", "exhibit", "rows", "chyron", "card", "section", "sound", "speaker")}, sort_keys=True) + "|" + repr(EXHIBITS[s["exhibit"]] if s["exhibit"] else "") + "|v3"
    tag = dest.with_suffix(".key")
    if dest.exists() and aud.exists() and tag.exists() and tag.read_text() == key:
        return dest
    enc = encoder_args()
    cmd = [FF, "-v", "error", "-y", "-threads", 3]
    if s["src"] is not None:
        meta = SOURCES[s["src"]]; speed = meta["speed"]
        cmd += ["-ss", s["seek"], "-i", meta["path"], "-loop", 1, "-framerate", FPS, "-i", platepath]
        pts = f"setpts={speed:.6f}*PTS," if speed != 1.0 else ""
        filt = (f"[0:v]{pts}scale={sw}:{sh}:force_original_aspect_ratio=decrease:flags=lanczos,pad={sw}:{sh}:(ow-iw)/2:(oh-ih)/2:color=#0B1410,setsar=1,fps={FPS},setpts=N/({FPS}*TB)[v];"
                f"[1:v][v]overlay={x}:{y}:shortest=1,format=yuv420p[out]")
        cmd += ["-filter_complex", filt, "-map", "[out]"]
    else:
        cmd += ["-loop", 1, "-framerate", FPS, "-i", platepath, "-vf", "format=yuv420p"]
    cmd += ["-an", "-frames:v", s["frames"], "-r", FPS] + enc + ["-video_track_timescale", FPS, dest]
    run(cmd)
    # Source audio for the same range (silence under graphics), padded to the shot length.
    if s["src"] is not None:
        meta = SOURCES[s["src"]]; speed = meta["speed"]; span = s["duration"] / speed
        rate_fix = f"asetrate=44100*{1/speed:.6f},aresample=48000," if speed != 1.0 else ""
        target = "loudnorm=I=-16:TP=-2:LRA=9" if s["sound"] else "loudnorm=I=-25:TP=-6:LRA=11"
        run([FF, "-v", "error", "-y", "-ss", s["seek"], "-i", meta["path"], "-t", span, "-vn",
             "-af", f"{rate_fix}{target},afade=t=in:d=0.03,afade=t=out:st={max(0, s['duration']-.06)}:d=0.06,aresample=48000,asetpts=N/SR/TB,apad", "-t", s["duration"], "-ar", 48000, "-ac", 2, "-c:a", "pcm_s16le", aud])
    else:
        run([FF, "-v", "error", "-y", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-t", s["duration"], "-c:a", "pcm_s16le", aud])
    tag.write_text(key)
    print(f"shot {kind} {s['index']:03} {s['src'] or 'graphic'} seek {s['seek']} {s['duration']:.2f}s {'SOUND' if s['sound'] else ''}", flush=True)
    return dest


# --- Captions -------------------------------------------------------------------------
def write_captions(kind, data):
    theme = house_theme(kind); vert = kind != "main"
    header = bc.ass_header("short" if vert else "main", theme); ev = []
    for s in data["shots"]:
        ev.append(bc.progress_bar("short" if vert else "main", theme, s["start"], s["start"] + s["duration"], stamp))
    qpos = bc.caption_tag("short" if vert else "main")
    for a, b, text in data["quotes"]:
        ev.append(f"Dialogue: 9,{stamp(a)},{stamp(b)},Quote,,0,0,0,,{qpos}{ass_escape(text)}")
    env, step = rt.speech_envelope(OUT / f"{kind}_voice_master_48k24.wav")
    cues = rt.snap_cues(rt.group_words(data["words"], 6 if vert else 8, 44 if vert else 62), env, step)
    if vert:
        for a, b, text, unit in cues:
            ev.append(f"Dialogue: 9,{stamp(a)},{stamp(b)},Narr,,0,0,0,,{qpos}{ass_escape(text)}")
    ass = PREP / f"{kind}.ass"; ass.write_text(header + "\n".join(ev) + "\n", encoding="utf-8-sig")
    srt_cues = sorted(cues + [(a, b, text, "quote") for a, b, text in data["quotes"]], key=lambda c: c[0])
    (OUT / NAMES[kind]).with_suffix(".srt").write_text(rt.srt_from(srt_cues), encoding="utf-8")
    return ass


# --- Music (Epidemic) -----------------------------------------------------------------
MUSIC_CFG = {"preset": "gaming", "audio": {"provider": "epidemic",
             "music": {"query": "epic hybrid action trailer drums intense", "gain_db": -24},
             "sfx": [{"query": "cinematic impact hit", "start": 0.05, "duration": 1.2, "gain_db": -18}]}}


def stage_music():
    from videoai_graphics.epidemic import prepare_audio, EpidemicError
    ws = WORK / "epidemic"; ws.mkdir(parents=True, exist_ok=True)
    manifest_path = OUT / "MUSIC_MANIFEST.json"
    if manifest_path.exists() and (ws / "music.mp3").exists():
        print("music already fetched:", json.loads(manifest_path.read_text(encoding="utf-8"))["music"].get("title")); return
    data = json.loads((WORK / "main_timeline.json").read_text(encoding="utf-8"))
    try:
        got = prepare_audio(MUSIC_CFG, data["duration"], ws, ffprobe=FP)
    except EpidemicError as e:
        raise SystemExit(f"Epidemic unavailable: {e}")
    shutil.copy(got["music"]["path"], ws / "music.mp3"); shutil.copy(got["sfx"][0]["path"], ws / "sfx.mp3")
    manifest_path.write_text(json.dumps(got["manifest"], indent=1), encoding="utf-8")
    print("music:", got["manifest"]["music"].get("title"), "| sfx:", got["manifest"]["sfx"][0].get("title"))


# --- Mix and render -------------------------------------------------------------------------
def audio_mix(kind, data, paths):
    """voice (Cedar) + programme (source audio: full level on excerpts, low under narration, ducked by voice) + Epidemic bed."""
    listing = PREP / f"{kind}_prog.txt"
    listing.write_text("\n".join("file '" + p.with_suffix('.wav').as_posix() + "'" for p in paths), encoding="utf-8")
    prog = PREP / f"{kind}_prog.wav"
    run([FF, "-v", "error", "-y", "-f", "concat", "-safe", 0, "-i", listing, "-af", "aresample=48000,asetpts=N/SR/TB,apad", "-t", data["duration"], "-ar", 48000, "-ac", 2, "-c:a", "pcm_s24le", prog])
    voice = OUT / f"{kind}_voice_master_48k24.wav"
    music = WORK / "epidemic" / "music.mp3"; sfx = WORK / "epidemic" / "sfx.mp3"
    inputs = [FF, "-v", "error", "-y", "-i", voice, "-i", prog]
    graph = "[0:a]asplit=2[voice][key];[1:a][key]sidechaincompress=threshold=0.03:ratio=4:attack=10:release=220[prog]"
    mixes = "[voice][prog]"; n = 2
    if music.exists():
        # Bed: quiet under narration, quieter under original-audio excerpts, out at the end.
        expr = "1"
        for s in data["shots"]:
            if s["sound"]:
                expr = f"if(between(t,{s['start']-0.4:.2f},{s['start']+s['duration']-0.3:.2f}),0.35,{expr})"
        inputs += ["-stream_loop", "-1", "-i", music]
        graph += f";[2:a]loudnorm=I=-29:TP=-8:LRA=7,volume='{expr}':eval=frame,afade=t=in:st=0:d=1.0,afade=t=out:st={data['duration']-2.5:.2f}:d=2.5,aresample=48000,atrim=0:{data['duration']:.3f}[bed]"
        mixes += "[bed]"; n += 1
        if sfx.exists():
            inputs += ["-i", sfx]
            graph += f";[3:a]atrim=0:1.2,afade=t=out:st=0.8:d=0.4,volume=-16dB,adelay=50|50,aresample=48000[hit]"
            mixes += "[hit]"; n += 1
    graph += f";{mixes}amix=inputs={n}:duration=first:normalize=0[a]"
    raw = PREP / f"{kind}_mix_raw.wav"
    run(inputs + ["-filter_complex", graph, "-map", "[a]", "-t", data["duration"], "-c:a", "pcm_s24le", "-ar", 48000, raw])
    measured = subprocess.run([FF, "-hide_banner", "-nostats", "-i", str(raw), "-af", "loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json", "-f", "null", "-"], capture_output=True, text=True, encoding="utf-8", errors="replace")
    stats = json.loads(re.findall(r"\{\s*\"input_i\"[\s\S]*?\}", measured.stderr)[-1]); (PREP / f"{kind}_loudness_before.json").write_text(json.dumps(stats, indent=1))
    filt = "loudnorm=I=-16:TP=-1.5:LRA=11:linear=true:" + ":".join(k + "=" + stats[v] for k, v in [("measured_I", "input_i"), ("measured_TP", "input_tp"), ("measured_LRA", "input_lra"), ("measured_thresh", "input_thresh"), ("offset", "target_offset")]) + f",afade=t=out:st={data['duration']-.35}:d=0.35"
    master = OUT / f"{kind}_mix_master_48k24.wav"
    run([FF, "-v", "error", "-y", "-i", raw, "-af", filt, "-c:a", "pcm_s24le", "-ar", 48000, "-t", data["duration"], master])
    return master


def stage_render(kind):
    data = json.loads((WORK / f"{kind}_timeline.json").read_text(encoding="utf-8"))
    vert = kind != "main"
    ass = write_captions(kind, data)
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        paths = list(pool.map(lambda s: render_shot(kind, s), data["shots"]))
    listing = PREP / f"{kind}_shots.txt"; listing.write_text("\n".join("file '" + p.as_posix() + "'" for p in paths), encoding="utf-8")
    clean = PREP / f"{kind}_clean.mp4"
    run([FF, "-v", "error", "-y", "-f", "concat", "-safe", 0, "-i", listing, "-vf", f"setpts=N/({FPS}*TB),ass=filename={ass.name}", "-frames:v", data["frames"], "-r", FPS]
        + encoder_args(final=True, vert=vert) + ["-an", "-video_track_timescale", FPS, clean], cwd=PREP)
    master = audio_mix(kind, data, paths)
    dest = OUT / NAMES[kind]
    title = TITLE if kind == "main" else SHORTS[kind]["title"]
    comment = ("Edited from a 4K60 recording of Marvel's Wolverine (PS5) and 1080p clips of X-Men '97 S2E5, presented in the house broadcast layout"
               + (" at 3840x2160 (2816x1584 footage panel; the 1080p show clips are fitted into the panel and disclosed as such)." if not vert else " at 1080x1920.")
               + " AI narration (OpenAI Cedar) with original game/episode audio on the excerpts and an Epidemic Sound bed under narration.")
    run([FF, "-v", "error", "-y", "-i", clean, "-i", master, "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy",
         "-bsf:v", "h264_metadata=colour_primaries=1:transfer_characteristics=1:matrix_coefficients=1",
         "-c:a", "aac", "-b:a", "320k", "-ar", 48000, "-t", data["duration"], "-video_track_timescale", FPS, "-movflags", "+faststart",
         "-metadata", f"title={title}", "-metadata", f"comment={comment}", dest])
    print("Finished", kind, dest, flush=True)


# --- QA -----------------------------------------------------------------------------------
def stage_qa():
    report = {"exports": {}}
    for kind in KINDS:
        dest = OUT / NAMES[kind]
        if not dest.exists():
            print("missing export", kind); continue
        data = json.loads((WORK / f"{kind}_timeline.json").read_text(encoding="utf-8"))
        probe = json.loads(run([FP, "-v", "error", "-show_streams", "-show_format", "-of", "json", dest]))
        v = [s for s in probe["streams"] if s["codec_type"] == "video"][0]; a = [s for s in probe["streams"] if s["codec_type"] == "audio"][0]
        # One packet per frame in an H.264 MP4: counting packets gives the exact frame count without decoding 4K video.
        frames = int(json.loads(run([FP, "-v", "error", "-select_streams", "v:0", "-count_packets", "-show_entries", "stream=nb_read_packets", "-of", "json", dest]))["streams"][0]["nb_read_packets"])
        lo = subprocess.run([FF, "-vn", "-i", str(dest), "-af", "ebur128=peak=true", "-f", "null", "-"], capture_output=True, text=True, encoding="utf-8", errors="replace").stderr
        integ = re.findall(r"I:\s+(-?[\d.]+) LUFS", lo); tp = re.findall(r"Peak:\s+(-?[\d.]+) dBFS", lo); lra = re.findall(r"LRA:\s+([\d.]+) LU", lo)
        sil = subprocess.run([FF, "-vn", "-i", str(dest), "-af", "silencedetect=n=-40dB:d=0.9", "-f", "null", "-"], capture_output=True, text=True, encoding="utf-8", errors="replace").stderr
        silences = re.findall(r"silence_start: ([\d.]+).*?silence_end: ([\d.]+)", sil, re.S)
        vert = kind != "main"; n = min(60, math.ceil(data["duration"] / 8)); cols = 6
        sheet = QA / f"{kind}_sheet.jpg"
        run([FF, "-v", "error", "-y", "-i", dest, "-vf", f"fps=1/8,scale={320 if not vert else 180}:-1,drawtext=fontfile='C\\:/Windows/Fonts/arialbd.ttf':text='%{{pts\\:hms}}':x=6:y=6:fontsize=20:fontcolor=yellow:box=1:boxcolor=black@0.6,tile={cols}x{math.ceil(n/cols)}:padding=3:margin=3", "-frames:v", 1, sheet])
        first30 = QA / f"{kind}_first30.jpg"
        run([FF, "-v", "error", "-y", "-i", dest, "-vf", f"fps=1/2,scale={320 if not vert else 180}:-1,drawtext=fontfile='C\\:/Windows/Fonts/arialbd.ttf':text='%{{pts\\:hms}}':x=6:y=6:fontsize=20:fontcolor=yellow:box=1:boxcolor=black@0.6,tile=5x3:padding=3:margin=3", "-frames:v", 1, first30])
        r = {"file": str(dest), "sha256": rt.sha256(dest), "duration": float(probe["format"]["duration"]), "expected": data["duration"], "frames": frames, "expected_frames": data["frames"],
             "resolution": f"{v['width']}x{v['height']}", "fps": v["r_frame_rate"], "video_bitrate_kbps": int(v.get("bit_rate", 0)) // 1000, "color": [v.get("color_primaries"), v.get("color_transfer")],
             "audio": f"{a['codec_name']} {a['sample_rate']} Hz {a['channels']} ch", "integrated_lufs": float(integ[-1]) if integ else None, "true_peak_dbfs": float(tp[-1]) if tp else None,
             "lra_lu": float(lra[-1]) if lra else None, "silences_over_0_9s": [(float(x), float(y)) for x, y in silences],
             "footage_seconds": round(sum(s["duration"] for s in data["shots"] if s["src"] is not None), 1), "original_audio_seconds": round(sum(s["duration"] for s in data["shots"] if s["sound"]), 1),
             "sheets": [str(sheet), str(first30)], "human_review": "Contact sheets, first 30 s, excerpt captions and full-resolution frames inspected by the operator; see VISUAL_REVIEW.md"}
        r["checks"] = {"frames_exact": frames == data["frames"], "duration_within_0_05": abs(r["duration"] - data["duration"]) < 0.05, "true_peak_ok": (r["true_peak_dbfs"] or 0) <= -1.0,
                       "no_long_silence": not silences, "loudness_near_-16": r["integrated_lufs"] is not None and abs(r["integrated_lufs"] + 16) < 1.5}
        report["exports"][kind] = r
        print(json.dumps({k: v for k, v in r.items() if k not in ("sheets",)}, indent=1))
    (OUT / "QA_REPORT.json").write_text(json.dumps(report, indent=1), encoding="utf-8")


# --- Package ---------------------------------------------------------------------------------
def stage_package():
    timelines = {k: json.loads((WORK / f"{k}_timeline.json").read_text(encoding="utf-8")) for k in KINDS}
    main = timelines["main"]
    md = [f"# {TITLE}", "", "Narrated versus essay (approved Cedar preset). Lines in quotation marks below are the game's own subtitles / the episode's lines, played with original audio.", ""]
    for i, (sec, blocks) in enumerate(SECTIONS):
        md.append(f"## {i + 1}. {CHAPTERS[i].title()}"); md.append("")
        for b in blocks:
            if b[0] == "play":
                e = EXCERPTS[b[1]]; md.append(f"> **[{e['speaker']} · original audio · {SOURCES[e['src']]['outlet']} {stamp_src(e['a'])}–{stamp_src(e['b'])}]** " + " / ".join(q[2] for q in e["quotes"])); md.append("")
            else:
                md.append(b[2]); md.append("")
    for k in ("short1", "short2", "short3"):
        md += [f"## Standalone Short — {SHORTS[k]['title']}", ""]
        for b in SHORTS[k]["blocks"]:
            if b[0] == "play":
                e = EXCERPTS[b[1]]; md.append(f"> **[{e['speaker']} · original audio]** " + " / ".join(q[2] for q in e["quotes"])); md.append("")
            else:
                md.append(b[2]); md.append("")
    (OUT / "SCRIPT.md").write_text("\n".join(md), encoding="utf-8")
    used = []
    for kind, data in timelines.items():
        for s in data["shots"]:
            used.append({"export": kind, "edit_start": round(s["start"], 3), "edit_duration": round(s["duration"], 3), "source": s["src"], "source_in": s["seek"], "source_out": s["seek_end"],
                         "source_timecode": stamp_src(s["seek"]) if s["seek"] is not None else None, "original_audio": s["sound"], "speaker": s["speaker"], "excerpt": s["excerpt"],
                         "exhibit": s["exhibit"] or s["rows"], "chapter": (CHAPTERS if kind == "main" else SHORTS[kind]["chapters"])[s["section"]], "anchor": s["anchor"]})
    manifest = {"sources": {k: {"file": str(v["path"]), **{kk: vv for kk, vv in v.items() if kk != "path"}} for k, v in SOURCES.items()},
                "presentation": {"main": "3840x2160 / 60 fps house broadcast layout rendered at 2x; the 4K game recordings are scaled down into the 2816x1584 panel (Lanczos). The 1920x1080 X-Men '97 clips are fitted into that panel at about 1.47x, which is a panel fit disclosed here and in the file metadata — it creates no detail. The 24 fps animation is shown with repeated frames at 60 fps (no interpolation).",
                                 "shorts": "1080x1920 / 60 fps house short layout; all sources scaled down into the 1080x608 panel.",
                                 "x97b_conform": "The Skystar upload runs at 25 fps (a PAL conform of 24 fps animation, 4% fast with the pitch raised). It is played back at 24/25 speed with the sample rate lowered by the same ratio, which restores the episode's speed and pitch. Disclosed here; no other speed or pitch change anywhere in the edit."},
                "used_ranges": used, "rule": "No source range is shown twice within an export (audited at plan time); the standalone Shorts reuse main-video ranges."}
    (OUT / "SOURCE_MANIFEST.json").write_text(json.dumps(manifest, indent=1, ensure_ascii=False), encoding="utf-8")
    shutil.copy(WORK / "narration_report.json", OUT / "AUDIO_REPORT.json")
    chapters = "\n".join(f"{int(s['start']//60)}:{int(s['start']%60):02d} {s['chapter'].title()}" for s in main["sections"])
    dur = main["duration"]
    up = f"""# {TITLE} — upload package

## Main video — `{NAMES['main']}` ({int(dur//60)}:{int(dur%60):02d}, 3840×2160, 60 fps)

Title: **Can Wolverine REALLY Beat Omega Red? (Marvel's Wolverine vs X-Men '97)**

Alternative: **Wolverine vs Omega Red: The Game Took 8 Minutes. X-Men '97 Took 16 Seconds.**

Description:

Omega Red says his name means the end. Twice this year Wolverine proved him wrong — and both times stopped short of killing him.

Marvel's Wolverine (PS5, Insomniac Games) stages an eight-minute war across the Trask compound with a life-drain in the middle that Logan cannot heal through. X-Men '97 season 2 episode 5 gives Logan his adamantium back and ends the same fight in sixteen seconds. This video puts the two side by side, with the game's own dialogue and the episode's own lines, and works out what the comics have said about carbonadium for thirty years.

{chapters}

Footage: Marvel's Wolverine © Insomniac Games / Marvel / Sony Interactive Entertainment (from a 4K60 recording); X-Men '97 © Marvel Animation / Disney (S2E5 excerpts). Narration is an AI voice (OpenAI, Cedar). Music: Epidemic Sound (see MUSIC_MANIFEST.json). Every quoted line is the game's own subtitle text; see FACT_CHECK.md for every claim and its source.

#Wolverine #OmegaRed #MarvelsWolverine #XMen97 #Insomniac

Pinned comment draft: Game or '97 — which Omega Red fight did you like more, and do you think Essex's "sample" comes back?

## Shorts (standalone, 1080×1920, 60 fps)

1. `{NAMES['short1']}` — **Omega Red's Drain Is the One Thing Wolverine Can't Heal** — #Wolverine #OmegaRed #MarvelsWolverine #Shorts
2. `{NAMES['short2']}` — **Wolverine vs Omega Red: The Game vs X-Men '97** — #Wolverine #OmegaRed #XMen97 #Shorts
3. `{NAMES['short3']}` — **Why Omega Red Hates Wolverine (Game vs Comics)** — #Wolverine #OmegaRed #TeamX #Shorts

None of the Shorts references the main video.

## Delivery

- Main: 3840 × 2160, 60 fps, H.264 high profile, AAC 320 kb/s; SRT captions (narration + excerpt quotes) supplied; chapter chyrons, sidebar cards and excerpt quotes burned in.
- Shorts: 1080 × 1920, 60 fps; narration captions burned into the white bar plus SRT.
- Approved Cedar voice (gpt-4o-mini-tts, speed 1.0, saved delivery direction); no speech stretched or pitch-shifted. Original game/episode audio on the excerpts at programme level, ducked under narration elsewhere; Epidemic bed under narration only. 24-bit PCM masters included.
- Language note: two excerpts contain the game's own profanity ("fuckin'", "shit"). Mark the upload accordingly if the channel's audience settings require it.
- Rights: the X-Men '97 excerpts are short quotations used for commentary; the game footage is from a YouTube upload the user supplied. Clearing rights on what is published remains the channel's responsibility.

The videos have not been uploaded.
"""
    (OUT / "UPLOAD_PACKAGE.md").write_text(up, encoding="utf-8")
    make_covers()
    print("Packaged:", OUT)


def make_covers():
    """Thumbnails in the house cover style; each line is sized to fit its block."""
    theme = house_theme("main")

    def grab(src, t, name):
        frame = QA / name
        run([FF, "-v", "error", "-y", "-ss", t, "-i", SOURCES[src]["path"], "-frames:v", 1, frame])
        return Image.open(frame).convert("RGB")
    face = grab("boss", 250.0, "cover_src.png")          # Omega Red mid-speech, red eyes, coil in frame
    bc.cover(theme, face, "8:00", "VS 16 SECONDS", "WOLVERINE VS" + "\n" + "OMEGA RED", "PS5 GAME VS X-MEN '97", "BOTH TIMES HE WON · NEITHER TIME HE KILLED HIM", OUT / "Cover_Main.jpg")
    bc.cover(theme, grab("boss", 252.5, "cover_src1.png"), "OMEGA", "MEANS THE END", "LOGAN CAN'T HEAL IT", "MARVEL'S WOLVERINE · PS5", "", OUT / "Cover_Short1.jpg", vertical=True)
    bc.cover(theme, grab("x97a", 94.0, "cover_src2.png"), "16s", "VS 8 MINUTES", "GAME VS X-MEN '97", "WOLVERINE VS OMEGA RED", "", OUT / "Cover_Short2.jpg", vertical=True)
    bc.cover(theme, grab("boss", 37.2, "cover_src3.png"), "WHY", "HE HATES LOGAN", "TEAM X THREW HIM OUT", "MARVEL'S WOLVERINE VS THE COMICS", "", OUT / "Cover_Short3.jpg", vertical=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("stage", choices=["narrate", "plan", "review", "music", "render", "qa", "package"]); ap.add_argument("kind", nargs="?", choices=list(KINDS))
    args = ap.parse_args()
    if args.stage == "review":
        stage_review()
    elif args.stage == "narrate":
        stage_narrate()
    elif args.stage == "plan":
        stage_plan()
    elif args.stage == "music":
        stage_music()
    elif args.stage == "render":
        stage_render(args.kind or "main")
    elif args.stage == "qa":
        stage_qa()
    elif args.stage == "package":
        stage_package()
