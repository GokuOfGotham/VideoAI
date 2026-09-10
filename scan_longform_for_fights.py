import os, subprocess, json
from combat_matrix_scanner import CombatMatrixScanner

movie_path = r"M:\Videos\Gaming\PlayStation 5\Batman Arkham Knight\Batman_ Arkham Knight (The Movie).mp4"
scanner = CombatMatrixScanner()

print("==================================================================")
print("  SCANNING 4K MOVIE FOR VERIFIED ACTIVE PHYSICAL COMBAT SCENES    ")
print("==================================================================")

verified_fights = []

# Scan every 2 minutes across the movie (from 10m to 120m)
for minute in range(10, 120, 2):
    sec = minute * 60
    res = scanner.evaluate_combat_segment(movie_path, sec, duration=30.0)
    if res["is_combat"] and res["confidence"] >= 60.0:
        mins = sec // 60
        print(f"  [+] FOUND VERIFIED COMBAT at t={mins:02d}:00 ({sec}s)! Confidence={res['confidence']}% | Hits={res['punch_hits_per_30s']}/30s")
        verified_fights.append({"sec": sec, "confidence": res["confidence"], "hits": res["punch_hits_per_30s"]})
        if len(verified_fights) >= 3:
            break
    else:
        mins = sec // 60
        # print rejection briefly
        # print(f"  [-] t={mins:02d}:00 ({sec}s) : {res['reason']}")

if not verified_fights:
    print("[!] No combat found in scanned chapters, expanding search...")
else:
    best_fight = max(verified_fights, key=lambda x: x["confidence"])
    print(f"\n[★] SELECTING BEST VERIFIED COMBAT SCENE: t={best_fight['sec']//60}m ({best_fight['sec']}s) with {best_fight['confidence']}% confidence!")
