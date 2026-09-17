"""The story spine: what a plan must say about its own structure, and the checks that run on it.

A spine is data the writer declares next to the production plan::

    {"title_question": "Can Wolverine really beat Omega Red?",
     "thesis": "Yes, twice this year, and neither time could he finish him.",
     "beats": [{"role": "hook", "at": 0, "text": "Omega Red's own line, original audio"},
               {"role": "claim", "at": 14, "text": "Yes. Twice. Neither time dead."},
               {"role": "evidence", "at": 40, "text": "X-Men #4, the coils, the drain"},
               {"role": "open_loop", "at": 590, "loop_id": "sample", "text": "Essex wants a sample"},
               {"role": "turn", "at": 330, "text": "In a straight drain, Wolverine loses"},
               {"role": "rehook", "at": 642, "text": "Now the other answer: X-Men '97"},
               {"role": "payoff", "at": 853, "text": "Same fight, two answers"},
               {"role": "close_loop", "at": 895, "loop_id": "sample", "text": "That's why Essex wants a sample"},
               {"role": "button", "at": 895, "text": "Watch what he does with it"}],
     "chapters": [{"title": "OMEGA MEANS THE END", "start": 0, "kind": "claim"}, ...]}

``validate_spine`` is deterministic and offline. It cannot judge whether the claim is interesting; it
can tell you the answer arrives late, the turn is missing, a loop was never closed, the same phrase
is doing the work three times, or the ending never returns to the title.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from typing import Dict, List, Optional

ROLES = {"hook", "question", "claim", "evidence", "turn", "rehook", "open_loop", "close_loop", "payoff", "button"}
CHAPTER_KINDS = {"question", "claim", "other"}
STOP = set("the a an of to in on at and or but is are was were be been it its this that these those he she they we you i his her their our your who what why how can does do did not no yes with from for as by so than then into out up down over under about".split())

ANSWER_DEADLINE = 15.0          # the claim (the answer to the title question) must land by here
TURN_WINDOW = (0.25, 0.70)      # fraction of the runtime in which the turn should fall
REHOOK_GAP_LONG = 180.0         # long form: no stretch longer than this without a question/rehook/turn/open_loop
EVIDENCE_GAP = 60.0             # no stretch longer than this without an evidence beat
BUTTON_TAIL = 0.12              # the button lives in the last 12 % of the runtime
LONG_FORM = 240.0               # runtime above which the long-form cadence rules apply


def key_tokens(text: str) -> set:
    return {t for t in re.findall(r"[a-z0-9']+", (text or "").lower()) if t not in STOP and len(t) > 2}


def _num(v, name, errors):
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
        errors.append(f"{name} must be a finite number"); return None
    return float(v)


def validate_spine(spine: Dict, duration: float, script: Optional[str] = None) -> Dict[str, List[str]]:
    """Returns {"errors": [...], "warnings": [...]}. Errors fail the policy check; warnings are printed."""
    errors: List[str] = []; warnings: List[str] = []
    if not isinstance(spine, dict):
        return {"errors": ["story_spine must be an object"], "warnings": []}
    duration = float(duration)
    title_q = str(spine.get("title_question", "")).strip()
    if len(title_q) < 8:
        errors.append("story_spine.title_question must state the question the title promises to answer")
    if len(str(spine.get("thesis", "")).strip()) < 12:
        errors.append("story_spine.thesis must state the answer in one sentence")
    beats = spine.get("beats")
    if not isinstance(beats, list) or not beats:
        errors.append("story_spine.beats must be a non-empty list"); return {"errors": errors, "warnings": warnings}
    clean = []
    for i, b in enumerate(beats):
        if not isinstance(b, dict) or b.get("role") not in ROLES:
            errors.append(f"beat {i}: role must be one of {sorted(ROLES)}"); continue
        at = _num(b.get("at"), f"beat {i}.at", errors)
        if at is None:
            continue
        if at < 0 or at > duration + 0.5:
            errors.append(f"beat {i} ({b['role']}): at={at:.1f}s is outside the {duration:.1f}s runtime"); continue
        if len(str(b.get("text", "")).strip()) < 4:
            errors.append(f"beat {i} ({b['role']}): text must describe the actual beat")
        clean.append(dict(b, at=at))
    if errors:
        return {"errors": errors, "warnings": warnings}
    clean.sort(key=lambda b: b["at"])
    by_role = lambda r: [b for b in clean if b["role"] == r]  # noqa: E731

    # 1. The hook is at zero and the answer arrives by the deadline.
    hooks = by_role("hook")
    if not hooks or hooks[0]["at"] > 0.5:
        errors.append("the first beat must be a hook at second zero")
    claims = by_role("claim") + by_role("payoff")
    if not claims:
        errors.append("no claim beat: the answer to the title question is never stated")
    elif min(b["at"] for b in claims) > ANSWER_DEADLINE:
        errors.append(f"first claim lands at {min(b['at'] for b in claims):.1f}s; the answer must be stated by {ANSWER_DEADLINE:.0f}s")

    # 2. A turn in the middle of the piece.
    turns = by_role("turn")
    if not turns:
        errors.append("no turn beat: nothing complicates the claim (a 'but' the viewer did not see coming)")
    else:
        lo, hi = TURN_WINDOW[0] * duration, TURN_WINDOW[1] * duration
        if not any(lo <= b["at"] <= hi for b in turns):
            warnings.append(f"no turn between {lo:.0f}s and {hi:.0f}s ({int(TURN_WINDOW[0]*100)}–{int(TURN_WINDOW[1]*100)} % of the runtime); the middle may sag")

    # 3. Re-hook cadence on long form.
    if duration > LONG_FORM:
        marks = sorted([0.0] + [b["at"] for b in clean if b["role"] in {"question", "rehook", "turn", "open_loop"}] + [duration])
        gaps = [(a, b) for a, b in zip(marks, marks[1:]) if b - a > REHOOK_GAP_LONG]
        for a, b in gaps:
            warnings.append(f"{a:.0f}s–{b:.0f}s runs {b-a:.0f}s without a new question, re-hook, turn or open loop")

    # 4. Evidence keeps coming.
    ev = sorted([0.0] + [b["at"] for b in clean if b["role"] == "evidence"] + [duration])
    for a, b in zip(ev, ev[1:]):
        if b - a > EVIDENCE_GAP and duration > 90:
            warnings.append(f"{a:.0f}s–{b:.0f}s runs {b-a:.0f}s without an evidence beat (a shown fact, quote or measurement)")

    # 5. Open loops close, later, and not in the same breath.
    opened = {}
    for b in clean:
        if b["role"] == "open_loop":
            lid = str(b.get("loop_id", "")).strip()
            if not lid:
                errors.append(f"open_loop at {b['at']:.0f}s needs a loop_id")
            else:
                opened.setdefault(lid, b["at"])
    for b in clean:
        if b["role"] == "close_loop":
            lid = str(b.get("loop_id", "")).strip()
            if lid not in opened:
                errors.append(f"close_loop '{lid}' at {b['at']:.0f}s closes a loop that was never opened")
            elif b["at"] < opened[lid] + 20:
                warnings.append(f"loop '{lid}' closes {b['at']-opened[lid]:.0f}s after it opens; that is a sentence, not a loop")
            else:
                opened.pop(lid)
    for lid, at in opened.items():
        errors.append(f"open loop '{lid}' (opened at {at:.0f}s) is never closed")

    # 6. The button returns to the title.
    buttons = by_role("button")
    if not buttons:
        errors.append("no button beat: the piece needs a last line, not a fade")
    else:
        last = max(buttons, key=lambda b: b["at"])
        if last["at"] < duration * (1 - BUTTON_TAIL):
            warnings.append(f"button at {last['at']:.0f}s sits before the last {int(BUTTON_TAIL*100)} % of the runtime")
        if title_q and not (key_tokens(title_q) & key_tokens(last.get("text", "") + " " + " ".join(b.get("text", "") for b in by_role("payoff")))):
            warnings.append("neither the payoff nor the button shares a key word with the title question; the ending may not feel like an answer")

    # 7. Chapters open on a question or a claim.
    chapters = spine.get("chapters") or []
    if chapters:
        other = [c.get("title", "?") for c in chapters if c.get("kind", "other") not in CHAPTER_KINDS or c.get("kind", "other") == "other"]
        if len(other) > max(1, len(chapters) // 3):
            warnings.append("chapters that are neither a question nor a claim: " + "; ".join(str(t) for t in other))

    # 8. Script-level tics.
    if script:
        warnings.extend(script_warnings(script))
    return {"errors": errors, "warnings": warnings}


def script_warnings(script: str) -> List[str]:
    """Repeated phrases, run-on sentences, stacked hedges — the things a read-aloud pass catches."""
    out: List[str] = []
    words = re.findall(r"[a-z0-9']+", script.lower())
    grams = Counter(" ".join(words[i:i + 4]) for i in range(len(words) - 3))
    repeats = [(g, n) for g, n in grams.items() if n >= 3 and not set(g.split()) <= STOP]
    for g, n in sorted(repeats, key=lambda x: -x[1])[:5]:
        out.append(f"phrase repeated {n}×: “{g}”")
    sentences = [s for s in re.split(r"(?<=[.!?])\s+", script.strip()) if s]
    long = [s for s in sentences if len(s.split()) > 32]
    if long:
        out.append(f"{len(long)} sentence(s) over 32 words; the longest starts “{long[0][:60]}…”")
    hedges = len(re.findall(r"\b(arguably|basically|essentially|it could be said|in many ways|kind of|sort of)\b", script.lower()))
    if hedges >= 3:
        out.append(f"{hedges} hedges (arguably / basically / sort of…); say the thing")
    return out


def template(duration: float = 600.0) -> Dict:
    """A skeleton to fill; blank texts deliberately fail validation."""
    return {"title_question": "", "thesis": "",
            "beats": [{"role": "hook", "at": 0, "text": ""}, {"role": "claim", "at": 12, "text": ""},
                      {"role": "evidence", "at": 45, "text": ""}, {"role": "turn", "at": round(duration * 0.45), "text": ""},
                      {"role": "rehook", "at": round(duration * 0.6), "text": ""}, {"role": "payoff", "at": round(duration * 0.9), "text": ""},
                      {"role": "button", "at": round(duration * 0.97), "text": ""}],
            "chapters": [{"title": "", "start": 0, "kind": "question"}]}


def report(result: Dict[str, List[str]]) -> str:
    lines = []
    for e in result.get("errors", []):
        lines.append("ERROR   " + e)
    for w in result.get("warnings", []):
        lines.append("warning " + w)
    return "\n".join(lines) if lines else "story spine: no findings"
