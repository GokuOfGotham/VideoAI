"""Excerpt-first drafting: rank the footage's own lines before the narration is written.

``candidates(scene_log, brief=...)`` groups consecutive dialogue into units that start and end on a
complete line, sets in/out on the measured word boundaries with a short lead and tail, and scores
each unit for quotability. The writer then builds the script around the top of that list instead of
hunting for lines afterwards. Output rows are ready for a recipe's EXCERPTS table::

    {"src": "boss", "a": 217.2, "b": 234.6, "speaker": "OMEGA RED / LOGAN",
     "quotes": [(0.28, 5.58, "Omega Red: You think I would die so easily?"), ...], "score": 7.5, ...}
"""
from __future__ import annotations

import re
from typing import Dict, Iterable, List, Optional

from .story import key_tokens

LEAD = 0.15   # seconds before the first word
TAIL = 0.35   # seconds after the last word
JOIN_GAP = 1.6  # lines closer than this (s) belong to the same exchange


def _score(unit: List[Dict], scene: Optional[Dict], brief_tokens: set) -> Dict:
    text = " ".join(l["text"] for l in unit)
    words = re.findall(r"[A-Za-z0-9']+", text)
    n = len(words)
    reasons = []; s = 0.0
    if re.search(r"[!?]", text):
        s += 2; reasons.append("exclamation/question")
    hits = key_tokens(text) & brief_tokens
    if hits:
        s += min(3, 1.5 * len(hits)); reasons.append("brief: " + ", ".join(sorted(hits)[:4]))
    if any(l.get("speaker") for l in unit):
        s += 1; reasons.append("speaker known")
    if len({l.get("speaker") for l in unit if l.get("speaker")}) >= 2:
        s += 1; reasons.append("exchange")
    if 4 <= n <= 30:
        s += 1
    elif n < 3:
        s -= 2; reasons.append("too short")
    elif n > 45:
        s -= 1; reasons.append("long")
    if re.search(r"\b(you|your)\b", text.lower()):
        s += 0.5; reasons.append("second person")
    if re.search(r"\b[A-Z][a-z]{2,}\b", " ".join(words[1:])):
        s += 0.5; reasons.append("names something")
    if scene:
        s += {"high": 1.0, "medium": 0.5}.get(scene.get("energy", ""), 0.0)
        if scene.get("kind") == "cutscene":
            s += 0.5
    last = unit[-1]["text"].strip()
    if len(last.split()) <= 5 and re.search(r"[.!?]$", last):
        s += 0.5; reasons.append("short last line")
    return {"score": round(s, 2), "reasons": reasons, "words": n}


def units_from_lines(lines: List[Dict], max_seconds: float = 20.0, join_gap: float = JOIN_GAP) -> List[List[Dict]]:
    """Consecutive lines that belong together; every unit starts and ends on a complete line."""
    units: List[List[Dict]] = []; cur: List[Dict] = []
    for ln in lines:
        if cur and (ln["start"] - cur[-1]["end"] > join_gap or ln["end"] - cur[0]["start"] > max_seconds):
            units.append(cur); cur = []
        cur.append(ln)
    if cur:
        units.append(cur)
    # also offer every multi-line unit's single best line on its own, so a tight Short can quote one beat
    singles = [[ln] for u in units if len(u) > 1 for ln in u if len(ln["text"].split()) >= 4]
    return units + singles


def candidates(log: Dict, *, src: str = "", brief: Iterable[str] = (), max_seconds: float = 20.0, lead: float = LEAD, tail: float = TAIL,
               speaker_upper: bool = True, limit: int = 40) -> List[Dict]:
    brief_tokens = set()
    for b in brief:
        brief_tokens |= key_tokens(b)
    scenes = {sc["index"]: sc for sc in log.get("scenes", [])}
    lines = [ln for ln in log.get("lines", []) if ln.get("text", "").strip()]
    out = []
    for unit in units_from_lines(lines, max_seconds=max_seconds):
        first, last = unit[0], unit[-1]
        w0 = (first.get("words") or [{"start": first["start"]}])[0]["start"]
        w1 = (last.get("words") or [{"end": last["end"]}])[-1]["end"]
        a = round(max(0.0, w0 - lead), 2); b = round(min(log.get("duration", w1 + tail), w1 + tail), 2)
        scene = scenes.get(first.get("scene"))
        sc = _score(unit, scene, brief_tokens)
        speakers = []
        for l in unit:
            sp = (l.get("speaker") or "").strip()
            if sp and sp not in speakers:
                speakers.append(sp)
        label = " / ".join(speakers) if speakers else "ORIGINAL AUDIO"
        quotes = [(round(l["start"] - a, 2), round(l["end"] - a, 2), (f"{l['speaker']}: " if l.get('speaker') and len(speakers) > 1 else "") + l["text"]) for l in unit]
        out.append({"src": src or log.get("label", ""), "a": a, "b": b, "seconds": round(b - a, 2), "speaker": label.upper() if speaker_upper else label,
                    "text": " / ".join(l["text"] for l in unit), "quotes": quotes, "scene": first.get("scene"),
                    "scene_description": (scene or {}).get("description", ""), **sc})
    out.sort(key=lambda r: (-r["score"], r["a"]))
    # drop near-duplicates (a single line already inside a higher-ranked unit)
    kept: List[Dict] = []
    for r in out:
        if any(k["a"] - 0.05 <= r["a"] and r["b"] <= k["b"] + 0.05 and k is not r for k in kept):
            continue
        kept.append(r)
        if len(kept) >= limit:
            break
    for i, r in enumerate(kept, 1):
        r["rank"] = i
    return kept


def markdown(rows: List[Dict], title: str = "Candidate excerpts") -> str:
    md = [f"# {title}", "", "Ranked by quotability. `a`/`b` are file seconds on measured word boundaries (lead {:.2f} s, tail {:.2f} s).".format(LEAD, TAIL), "",
          "| rank | score | src | in–out | s | speaker | line | why |", "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        md.append(f"| {r['rank']} | {r['score']} | {r['src']} | {r['a']:.2f}–{r['b']:.2f} | {r['seconds']:.1f} | {r['speaker']} | {r['text'].replace('|','/')} | {', '.join(r['reasons'])} |")
    return "\n".join(md) + "\n"
