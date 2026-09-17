"""The director's review: a punch list against the footage, before the render.

``digest(plan, timeline, scene_logs)`` folds a recipe's plan (narration, review, chapters) and its
timeline (every shot with source, seek, duration, sound) together with the scene logs, so that each
shot carries what is actually on screen at that seek and what is said. ``director_review`` sends that
digest to a chat model with a brief that asks for the things a good editor flags on a first watch:

* claims in the narration that nothing on screen supports at that moment,
* stretches longer than twenty seconds without a new idea or a new picture,
* phrases doing the same job twice, chapter titles that are neither a question nor a claim,
* a turn that does not turn, an ending that does not answer the title,
* excerpts that run past their best line, and the one line a viewer would quote.

The deterministic spine checks (``story.validate_spine``) are prepended, so the report is useful even
when the model is unavailable. One chat call per review; nothing here alters the plan.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict, List, Optional

from . import story

REVIEW_MODEL = os.getenv("DIRECTOR_REVIEW_MODEL", "gpt-4.1")

BRIEF = (
    "You are the director reviewing a narrated video essay before it renders. You get the plan (title, thesis, chapters, "
    "narration by unit, story beats) and the timeline (every shot in order with its source, timecode, duration, whether its "
    "original audio plays, and — where a scene log exists — what is on screen and what is said). Judge the cut like a first-time "
    "viewer and an experienced editor at once. Return JSON only:\n"
    '{"summary": "<three sentences: what works, the biggest weakness, the one change that matters most>",\n'
    ' "quotable_line": "<the single narration or excerpt line a viewer would repeat>",\n'
    ' "retention_risk": [{"at": <seconds>, "why": "<why a viewer leaves here>"}],\n'
    ' "findings": [{"severity": "fix|consider", "at": <seconds>, "where": "<unit or shot id>", "kind": "unsupported_claim|dead_stretch|repeat|chapter_title|turn|ending|excerpt_length|pacing|clarity|other",\n'
    '               "issue": "<what is wrong, specific>", "suggestion": "<the concrete change: a line rewrite, a different shot from the scene log, a trim with times>"}]}\n'
    "Rules: cite times. Prefer suggestions that use the scene log (name the scene index and what it shows). Do not praise. "
    "Flag any narration claim about what is on screen that the shot at that time does not show. Flag every 4-word phrase used three or more times. "
    "Flag chapters whose title is neither a question nor a claim. Flag the ending if it does not answer the title question in its own words. "
    "Keep findings under 25; order by importance."
)


def _scene_at(log: Optional[Dict], t: float) -> Optional[Dict]:
    if not log:
        return None
    for sc in log.get("scenes", []):
        if sc["start"] <= t < sc["end"]:
            return sc
    return None


def digest(plan: Dict, timeline: Dict, scene_logs: Optional[Dict[str, Dict]] = None, unit_texts: Optional[Dict[str, str]] = None) -> Dict:
    """A compact, time-ordered view of the cut for the reviewer (human or model)."""
    scene_logs = scene_logs or {}
    review = plan.get("production_review", {})
    out = {"title": plan.get("title"), "duration": timeline.get("duration"), "content_type": review.get("content_type"), "format": review.get("format"),
           "hook": review.get("hook"), "first_payoff": review.get("first_payoff"), "story_spine": plan.get("story_spine"),
           "chapters": [{"start": round(s.get("start") or 0, 1), "title": s.get("chapter")} for s in timeline.get("sections", [])],
           "narration_units": [], "shots": []}
    seen = set()
    for w in timeline.get("words", []):
        u = w.get("unit")
        if u and u not in seen:
            seen.add(u)
            out["narration_units"].append({"unit": u, "start": round(w["start"], 1), "text": (unit_texts or {}).get(u, "")})
    if unit_texts is None:
        # reconstruct from the timed words when the recipe did not pass its texts
        texts: Dict[str, List[str]] = {}
        for w in timeline.get("words", []):
            texts.setdefault(w.get("unit", ""), []).append(w["word"])
        for u in out["narration_units"]:
            u["text"] = " ".join(texts.get(u["unit"], []))
    for s in timeline.get("shots", []):
        row = {"id": s.get("index"), "start": round(s["start"], 1), "seconds": round(s["duration"], 1), "source": s.get("src") or "graphic",
               "seek": s.get("seek"), "sound": bool(s.get("sound")), "unit": s.get("unit"), "anchor": s.get("anchor"),
               "graphic": s.get("exhibit") or s.get("rows"), "chyron": s.get("chyron")}
        sc = _scene_at(scene_logs.get(s.get("src") or ""), s["seek"]) if s.get("seek") is not None else None
        if sc:
            row["on_screen"] = sc.get("description"); row["scene"] = sc.get("index"); row["kind"] = sc.get("kind")
            row["said"] = [((d.get("speaker") + ": ") if d.get("speaker") else "") + d["text"] for d in sc.get("dialogue", []) if s["seek"] - 0.5 <= d["start"] <= (s.get("seek_end") or s["seek"] + s["duration"]) + 0.5]
        if s.get("excerpt"):
            row["excerpt"] = s["excerpt"]
        out["shots"].append(row)
    return out


def chat_json(system: str, user: str, model: str = REVIEW_MODEL) -> Dict:
    import requests
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("OPENAI_API_KEY is required for the director review")
    r = requests.post("https://api.openai.com/v1/chat/completions", headers={"Authorization": f"Bearer {key}"},
                      json={"model": model, "response_format": {"type": "json_object"}, "temperature": 0.3,
                            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}, timeout=300)
    r.raise_for_status()
    return json.loads(r.json()["choices"][0]["message"]["content"])


def director_review(plan: Dict, timeline: Dict, scene_logs: Optional[Dict[str, Dict]] = None, *, unit_texts: Optional[Dict[str, str]] = None,
                    model: str = REVIEW_MODEL, call=chat_json) -> Dict:
    """Deterministic spine findings + the model's punch list. ``call`` is injectable for tests."""
    d = digest(plan, timeline, scene_logs, unit_texts)
    script = " ".join(u["text"] for u in d["narration_units"])
    result = {"spine": None, "model": model, "review": None}
    if plan.get("story_spine"):
        result["spine"] = story.validate_spine(plan["story_spine"], float(timeline.get("duration") or 0), script)
    else:
        result["spine"] = {"errors": ["no story_spine in the plan"], "warnings": story.script_warnings(script)}
    result["review"] = call(BRIEF, json.dumps(d, ensure_ascii=False))
    return result


def markdown(result: Dict, title: str = "Director review") -> str:
    md = [f"# {title}", "", f"Model: `{result.get('model')}` · deterministic checks from `videoai_director.story`", ""]
    sp = result.get("spine") or {}
    md += ["## Story spine", ""]
    for e in sp.get("errors", []):
        md.append(f"- **ERROR** {e}")
    for w in sp.get("warnings", []):
        md.append(f"- warning: {w}")
    if not sp.get("errors") and not sp.get("warnings"):
        md.append("- no findings")
    rv = result.get("review") or {}
    md += ["", "## Summary", "", str(rv.get("summary", "")), "", f"**Quotable line:** {rv.get('quotable_line', '')}", ""]
    if rv.get("retention_risk"):
        md += ["## Retention risk", ""] + [f"- {r.get('at')}s — {r.get('why')}" for r in rv["retention_risk"]] + [""]
    md += ["## Findings", "", "| # | severity | at | where | kind | issue | suggestion |", "|---|---|---|---|---|---|---|"]
    for i, f in enumerate(rv.get("findings", []), 1):
        md.append(f"| {i} | {f.get('severity')} | {f.get('at')} | {str(f.get('where','')).replace('|','/')} | {f.get('kind')} | {str(f.get('issue','')).replace('|','/')} | {str(f.get('suggestion','')).replace('|','/')} |")
    return "\n".join(md) + "\n"
