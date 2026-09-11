"""Build timed, resolution-aware graphic overlays and captions as ASS subtitles.

This module only constructs strings. It does not load credentials, write assets,
import the video-generation pipelines, or call external services.
"""

from __future__ import annotations

import math
import re
import unicodedata
from typing import Any

PRESETS = {
    "political": {"accent": "EF4444", "ink": "F8FAFC", "panel": "111827", "label": "ANALYSIS"},
    "space": {"accent": "38BDF8", "ink": "F1F5F9", "panel": "0C172B", "label": "MISSION BRIEF"},
    "gaming": {"accent": "B7F34A", "ink": "F8FAFC", "panel": "101815", "label": "PLAY BY PLAY"},
    "reaction": {"accent": "B79CFF", "ink": "FAF5FF", "panel": "1C1530", "label": "COMMENTARY"},
}
KINDS = {"lower_third", "title_card", "callout", "badge", "ticker", "progress_bar", "reaction_frame"}


def _number(value: Any, name: str, minimum: float = 0, maximum: float = 86400) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite number")
    try:
        value = float(value)
    except OverflowError:
        raise ValueError(f"{name} must be a finite number") from None
    if not math.isfinite(value) or not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


def _color(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"#?[0-9a-fA-F]{6}", value):
        raise ValueError("colors must be six-digit RGB hex values")
    value = value.lstrip("#").upper()
    return value[4:6] + value[2:4] + value[:2]


def _plain(value: Any, name: str = "text", max_length: int = 320) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be text")
    if len(value) > max_length:
        raise ValueError(f"{name} exceeds {max_length} characters; split it into another cue")
    # Literal lookalikes cannot be interpreted as ASS overrides or line escapes.
    value = "".join(c for c in value if c.isspace() or unicodedata.category(c) != "Cc")
    return " ".join(value.replace("\\", "＼").replace("{", "｛").replace("}", "｝").split())


def _time(seconds: float) -> str:
    ticks = int(round(seconds * 100))
    hours, ticks = divmod(ticks, 360000)
    minutes, ticks = divmod(ticks, 6000)
    secs, centis = divmod(ticks, 100)
    return f"{hours}:{minutes:02}:{secs:02}.{centis:02}"


def _measure(text: str, size: float) -> float:
    weights = {" ": .32, "I": .34, "i": .27, "l": .27, "t": .36, ".": .3, ",": .3, "!": .34}
    return sum(weights.get(c, .98 if c in "MWmw@%" else .73 if c.isupper() else .61) for c in text) * size


def _fit(text: str, width: float, font_size: float, *, max_lines: int = 2) -> tuple[list[str], float]:
    for factor in (1, .94, .87, .80, .73):
        size = font_size * factor
        lines: list[str] = []
        current = ""
        for word in text.split():
            if _measure(word, size) > width:
                current = "!OVERSIZE!"
                break
            trial = f"{current} {word}".strip()
            if current and _measure(trial, size) > width:
                lines.append(current)
                current = word
            else:
                current = trial
        if current:
            lines.append(current)
        if len(lines) <= max_lines and "!OVERSIZE!" not in lines:
            return lines, size
    raise ValueError("overlay text is too long for its region; shorten it or split it into cues")


def _event(start: float, end: float, text: str, layer: int = 10) -> dict:
    return {"layer": layer, "start": start, "end": end, "text": text}


def _position(x: float, y: float, animate: bool, scale: float) -> str:
    if animate:
        return f"\\move({x-22*scale:.2f},{y:.2f},{x:.2f},{y:.2f},0,220)"
    return f"\\pos({x:.2f},{y:.2f})"


def _box(start: float, end: float, x: float, y: float, w: float, h: float,
         color: str, scale: float, *, alpha: str = "12", layer: int = 10,
         animate: bool = True, outline: bool = False) -> dict:
    if outline:
        path = f"m 0 0 l {w:.2f} 0 {w:.2f} {h:.2f} 0 {h:.2f} 0 0"
        tags = f"\\1a&HFF&\\3a&H00&\\3c&H{_color(color)}&\\bord{3*scale:.2f}"
    else:
        path = f"m 0 0 l {w:.2f} 0 {w:.2f} {h:.2f} 0 {h:.2f}"
        tags = f"\\1c&H{_color(color)}&\\1a&H{alpha}&\\bord0"
    return _event(start, end,
                  "{" + "\\an7" + _position(x, y, animate, scale)
                  + f"\\p1\\shad0\\fad(150,140){tags}" + "}" + path + "{\\p0}", layer)


def _text(start: float, end: float, text: str, x: float, y: float,
          width: float, size: float, color: str, scale: float, *,
          font: str = "Arial", bold: bool = True, max_lines: int = 2,
          animate: bool = True, layer: int = 12) -> tuple[list[dict], float]:
    lines, size = _fit(text, width, size, max_lines=max_lines)
    events = []
    for i, line in enumerate(lines):
        pos = _position(x, y + i * size * 1.19, animate, scale)
        tags = f"\\an7{pos}\\fn{font}\\fs{size:.2f}\\b{int(bold)}\\c&H{_color(color)}&\\bord0\\shad0\\fad(150,140)"
        events.append(_event(start, end, "{" + tags + "}" + line, layer))
    return events, len(lines) * size * 1.19


def _overlay(cue: dict, width: int, height: int, theme: dict, font: str) -> list[dict]:
    kind, start, end = cue["type"], cue["start"], cue["end"]
    scale = min(width, height) / 1080
    margin = 64 * scale
    accent = cue.get("color", theme["accent"])
    _color(accent)
    panel, ink = theme["panel"], theme["ink"]
    title = _plain(cue.get("title", cue.get("text", "")), "overlay title")
    subtitle = _plain(cue.get("subtitle", ""), "overlay subtitle")
    label = _plain(cue.get("label", theme["label"]), "overlay label", 50).upper()
    default_w = width - 2 * margin
    x = _number(cue.get("x", margin / width), "overlay x", 0, 1) * width
    w = _number(cue.get("width", default_w / width), "overlay width", .1, 1) * width
    w = min(w, width - x - margin)
    if w < 160 * scale:
        raise ValueError("overlay region is too narrow or outside the canvas")
    default_y = {"lower_third": .60, "title_card": .33, "callout": .18,
                 "badge": .07, "ticker": .935 if height > width else .91, "progress_bar": .965,
                 "reaction_frame": .12}[kind]
    y = _number(cue.get("y", default_y), "overlay y", 0, .97) * height
    events: list[dict] = []
    if kind == "lower_third":
        if not title:
            raise ValueError("lower_third requires a title")
        title_events, title_h = _text(start, end, title, x+25*scale, y+37*scale,
                                      w-50*scale, 46*scale, ink, scale, font=font)
        subtitle_events, sub_h = _text(start, end, subtitle, x+25*scale, y+40*scale+title_h,
                                       w-50*scale, 25*scale, "CBD5E1", scale, font=font, bold=False, max_lines=1)
        panel_h = max(116*scale, 56*scale+title_h+sub_h)
        if y + panel_h > height*.735:
            if "y" not in cue and panel_h < height*.5:
                lifted = {**cue,"y":max(.12,(height*.73-panel_h)/height)}
                return _overlay(lifted,width,height,theme,font)
            raise ValueError("lower-third text intrudes into caption safe area; shorten it or move y upward")
        events.extend([_box(start,end,x,y,w,panel_h,panel,scale),
                       _box(start,end,x,y,5*scale,panel_h,accent,scale,alpha="00",layer=11)])
        events.extend(_text(start,end,label,x+25*scale,y+11*scale,w-50*scale,19*scale,accent,scale,font=font,max_lines=1)[0])
        events.extend(title_events + subtitle_events)
    elif kind == "title_card":
        if not title:
            raise ValueError("title_card requires a title")
        title_events, title_h = _text(start,end,title,x+36*scale,y+65*scale,w-72*scale,
                                     66*scale,ink,scale,font=font,max_lines=3)
        subtitle_events, sub_h = _text(start,end,subtitle,x+36*scale,y+82*scale+title_h,w-72*scale,
                                       29*scale,"CBD5E1",scale,font=font,bold=False,max_lines=2)
        panel_h = 111*scale+title_h+sub_h
        if y+panel_h > height*.76:
            raise ValueError("title card is too tall; shorten text or move y upward")
        events.extend([_box(start,end,x,y,w,panel_h,panel,scale,alpha="06"),
                       _box(start,end,x,y,w,5*scale,accent,scale,alpha="00",layer=11)])
        events.extend(_text(start,end,label,x+36*scale,y+26*scale,w-72*scale,22*scale,accent,scale,font=font,max_lines=1)[0])
        events.extend(title_events+subtitle_events)
    elif kind == "callout":
        if not title:
            raise ValueError("callout requires a title")
        w = min(w, width*.74)
        title_events, title_h = _text(start,end,title,x+24*scale,y+48*scale,w-48*scale,
                                     37*scale,ink,scale,font=font)
        subtitle_events, sub_h = _text(start,end,subtitle,x+24*scale,y+59*scale+title_h,w-48*scale,
                                       25*scale,"CBD5E1",scale,font=font,bold=False,max_lines=2)
        panel_h = 78*scale+title_h+sub_h
        if y+panel_h > height-margin:
            raise ValueError("callout exceeds canvas height")
        events.extend([_box(start,end,x,y,w,panel_h,panel,scale),
                       _box(start,end,x,y,5*scale,panel_h,accent,scale,alpha="00",layer=11)])
        events.extend(_text(start,end,label,x+24*scale,y+16*scale,w-48*scale,19*scale,accent,scale,font=font,max_lines=1)[0])
        events.extend(title_events+subtitle_events)
    elif kind == "badge":
        badge = title or label
        badge_w = min(w, _measure(badge,24*scale)+36*scale)
        if y+46*scale > height-8*scale:
            raise ValueError("badge exceeds canvas height")
        events.append(_box(start,end,x,y,badge_w,46*scale,accent,scale,alpha="00"))
        events.extend(_text(start,end,badge,x+18*scale,y+9*scale,badge_w-30*scale,24*scale,
                            panel,scale,font=font,max_lines=1)[0])
    elif kind == "ticker":
        if not title:
            raise ValueError("ticker requires title or text")
        h = 42*scale
        if y+h > height-8*scale:
            raise ValueError("ticker exceeds canvas height")
        events.append(_box(start,end,x,y,w,h,panel,scale,animate=False))
        # Clip the motion to the ticker lane. Source text is sanitized above.
        travel = _measure(title,25*scale)
        duration_ms = round((end-start)*1000)
        tags = (f"\\an7\\move({x+w:.2f},{y+7*scale:.2f},{x-travel:.2f},{y+7*scale:.2f},0,{duration_ms})"
                f"\\clip({x:.2f},{y:.2f},{x+w:.2f},{min(height,y+h):.2f})"
                f"\\fn{font}\\fs{25*scale:.2f}\\b1\\c&H{_color(ink)}&\\bord0\\shad0")
        events.append(_event(start,end,"{"+tags+"}"+title,12))
    elif kind == "progress_bar":
        h = max(3, 5*scale)
        if y+h > height-8*scale:
            raise ValueError("progress bar exceeds canvas height")
        events.append(_box(start,end,x,y,w,h,"334155",scale,animate=False,alpha="20",layer=3))
        # Clip a full-width vector to an animated rectangle rather than resizing text.
        ms = round((end-start)*1000)
        tags = (f"\\an7\\pos({x:.2f},{y:.2f})\\p1\\bord0\\shad0\\c&H{_color(accent)}&"
                f"\\clip({x:.2f},{y:.2f},{x:.2f},{y+h:.2f})"
                f"\\t(0,{ms},\\clip({x:.2f},{y:.2f},{x+w:.2f},{y+h:.2f}))")
        events.append(_event(start,end,"{"+tags+"}"+f"m 0 0 l {w:.2f} 0 {w:.2f} {h:.2f} 0 {h:.2f}"+"{\\p0}",4))
    elif kind == "reaction_frame":
        # Decorative inset outline; inset video itself must already be composited.
        w = min(w,width*.32)
        h = w*.75
        if y+h+48*scale > height-margin:
            raise ValueError("reaction frame exceeds canvas height")
        events.append(_box(start,end,x,y,w,h,accent,scale,alpha="FF",outline=True,animate=False))
        events.append(_box(start,end,x,y+h,w,42*scale,accent,scale,alpha="00",animate=False))
        events.extend(_text(start,end,title or "REACTION",x+12*scale,y+h+8*scale,w-24*scale,
                            21*scale,panel,scale,font=font,max_lines=1,animate=False)[0])
    return events


def compile_graphics(config: dict, width: int, height: int, duration: float | None = None) -> dict:
    """Compile a graphics cue sheet without starting any video or API work."""
    if not isinstance(config,dict):
        raise ValueError("graphics config must be a JSON object")
    for name, value in (("width",width),("height",height)):
        if isinstance(value,bool) or not isinstance(value,int) or not 320 <= value <= 8192:
            raise ValueError(f"{name} must be an integer between 320 and 8192")
    preset = config.get("preset","gaming")
    if not isinstance(preset,str) or preset not in PRESETS:
        raise ValueError("preset must be political, space, gaming, or reaction")
    theme = PRESETS[preset]
    font = config.get("font_name","Arial")
    if not isinstance(font,str) or not re.fullmatch(r"[A-Za-z0-9 _-]{1,60}",font):
        raise ValueError("font_name must be a plain font family name")
    overlays = config.get("overlays",[])
    words = config.get("words",[])
    if not isinstance(overlays,list) or len(overlays)>1000:
        raise ValueError("overlays must be a list of at most 1000 cues")
    if not isinstance(words,list):
        raise ValueError("words must be a list of word/start/end objects")
    prepared=[]
    ends=[]
    for i,cue in enumerate(overlays):
        if not isinstance(cue,dict) or not isinstance(cue.get("type"),str) or cue.get("type") not in KINDS:
            raise ValueError(f"overlay {i} requires one of these types: {', '.join(sorted(KINDS))}")
        cue=dict(cue)
        cue["start"]=_number(cue.get("start"),f"overlay {i} start")
        cue["end"]=_number(cue.get("end"),f"overlay {i} end")
        if cue["end"]-cue["start"]<.02:
            raise ValueError(f"overlay {i} must last at least 0.02 seconds")
        ends.append(cue["end"])
        prepared.append(cue)
    for i,word in enumerate(words):
        if not isinstance(word,dict):
            raise ValueError(f"word {i} must be an object")
        ends.append(_number(word.get("end"),f"word {i} end"))
    length = _number(duration if duration is not None else config.get("duration",max(ends,default=8.0)),
                     "duration",.02)
    if any(end>length+.000001 for end in ends):
        raise ValueError("a graphics or caption cue ends after the video duration")
    events=[]
    for cue in prepared:
        cue["end"]=min(cue["end"],length)
        if round(cue["end"]*100)<=round(cue["start"]*100):
            raise ValueError("a graphics cue is too short to display within the video")
        events.extend(_overlay(cue,width,height,theme,font))
    from .captions import build_captions
    options=config.get("captions",{})
    if not isinstance(options,dict):
        raise ValueError("captions must be an options object")
    options={"font_name":font,**options}
    captions=build_captions(words,width,height,preset,options,duration=length)
    events.extend(captions["events"])
    header=("[Script Info]\nTitle: VideoAI Graphics\nScriptType: v4.00+\nWrapStyle: 2\n"
            f"PlayResX: {width}\nPlayResY: {height}\nScaledBorderAndShadow: yes\n\n"
            "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
            f"Style: Default,{font},48,&H00FFFFFF,&H00FFFFFF,&H00000000,&H90000000,-1,0,0,0,100,100,0,0,1,2,0,2,40,40,80,1\n\n"
            "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")
    lines=[]
    for event in sorted(events,key=lambda e:(e["start"],e["layer"],e["end"])):
        start=max(0,event["start"])
        end=min(length,event["end"])
        if round(end*100)<=round(start*100):
            continue
        lines.append(f"Dialogue: {event['layer']},{_time(start)},{_time(end)},Default,,0,0,0,,{event['text']}")
    return {"ass":header+"\n".join(lines)+"\n","srt":captions["srt"],
            "duration":length,"overlay_count":len(overlays),"caption_count":len(captions["groups"])}
