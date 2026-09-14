"""House graphics for every VideoAI production: the "broadcast" system.

One layout, one type system, one set of components for politics, science,
gaming, sports or anything else; only the accent colours and labels change
per subject. The look is modelled on NBC News NOW and MS NOW graphics: bold
condensed uppercase chyrons on solid bars, a coloured kicker tab, a white
headline bar, a white sidebar card, and full-screen numbers as big condensed
type on a dark ground. Footage is boxed with its own on-screen graphics intact
(the way MS NOW shows other networks' clips) and labelled underneath.

Only Pillow is needed. Rendering a plate returns the PNG path and the panel
rectangle the footage should be overlaid into; captions are burned by the
caller with the ASS header and tag from `ass_header` / `caption_tag`.

    from videoai_graphics.broadcast import Theme, Shot, render_plate
    theme = Theme(subject="science", channel="MY CHANNEL", series="ROGUE WAVES",
                  chapters=["THE WALL OF WATER", "THE PHYSICS"])
    shot = Shot(kind="main", section=0, card=Card("THE MEASUREMENT", "25.6 METRES",
                ["Draupner platform, 1995", "First instrument record"], "Statoil laser gauge"),
                source=Source("BBC", "Horizon", "March 3, 2026", "1920x1080"), sound=False)
    png, (x, y, w, h) = render_plate(theme, shot, Path("plate.png"))

Run `python -m videoai_graphics.broadcast --demo out_dir` to render sample
plates for the four built-in subjects.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Sequence, Tuple

from PIL import Image, ImageDraw, ImageFont

__all__ = ["SUBJECTS", "Theme", "Card", "Source", "Shot", "Exhibit", "render_plate", "ass_header",
           "caption_tag", "progress_bar", "cover", "MAIN_LAYOUT", "SHORT_LAYOUT"]

# --- Palette and type ---------------------------------------------------------------
WHITE = "#FFFFFF"; CARD = "#F5F7FB"; INK = "#101418"; GRAY = "#5B6B85"; RULE = "#D6DCE8"
# accent = tabs, kickers, progress; accent2 = original-audio / alert tab; ground = frame; ground2 = lower band; panel = graphic box
SUBJECTS = {
    "politics": dict(accent="#1B4ED8", accent_hi="#2F6BFF", accent2="#D62828", ground="#0B1730", ground2="#08122A", panel="#0E1E44", navy="#0F2452", mute="#9FB0CC", edge="#3A4B6E"),
    "science":  dict(accent="#0284C7", accent_hi="#38BDF8", accent2="#F59E0B", ground="#07142A", ground2="#050E1F", panel="#0B1F3F", navy="#0B2A4A", mute="#9CB8D0", edge="#2E4A6B"),
    "gaming":   dict(accent="#5FB824", accent_hi="#A3E635", accent2="#E11D74", ground="#0B1410", ground2="#070D0A", panel="#10241A", navy="#14301F", mute="#A6C3AE", edge="#2F4A38"),
    "sports":   dict(accent="#E8590C", accent_hi="#FF8A3D", accent2="#1B4ED8", ground="#0E0F1A", ground2="#090A12", panel="#1B1D33", navy="#2A1A0F", mute="#C2B8B0", edge="#4A3A32"),
    "default":  dict(accent="#3B6FD6", accent_hi="#5B8DEF", accent2="#D62828", ground="#0B1730", ground2="#08122A", panel="#0E1E44", navy="#0F2452", mute="#9FB0CC", edge="#3A4B6E"),
}
FONT_DIR = Path("C:/Windows/Fonts")
FONTS = {"cond": "RobotoCondensed-Bold.ttf", "bold": "Roboto-Bold.ttf", "reg": "Roboto-Regular.ttf", "num": "bahnschrift.ttf"}
FALLBACKS = {"cond": "ARIALNB.TTF", "bold": "arialbd.ttf", "reg": "arial.ttf", "num": "impact.ttf"}

# Main (1920x1080): panel 1408x792 at (56,96); sidebar 368 wide; tab row 904; white bar 952-1024; strap 1040.
MAIN_LAYOUT = dict(W=1920, H=1080, px=56, py=96, pw=1408, ph=792, sx=1496, sy=96, sw=368, sh=928, tab_y=904, bar_y=952, bar_h=72, strap_y=1040, cap_x=80, cap_y=988)
# Short (1080x1920): panel full width at 380; tab row 1004; white bar 1052-1144; card 1184-1500; strap 1560.
SHORT_LAYOUT = dict(W=1080, H=1920, px=0, py=380, pw=1080, ph=608, tab_y=1004, bar_y=1052, bar_h=92, card_y=1184, card_h=316, strap_y=1560, cap_x=28, cap_y=1098)


def font(kind: str, size: float) -> ImageFont.FreeTypeFont:
    p = FONT_DIR / FONTS[kind]
    if not p.exists():
        p = FONT_DIR / FALLBACKS[kind]
    f = ImageFont.truetype(str(p), round(size))
    if kind == "num":
        try:
            f.set_variation_by_name("Bold Condensed")
        except Exception:
            pass
    return f


@dataclass
class Theme:
    subject: str = "default"          # key of SUBJECTS
    channel: str = "CIVIC CONTEXT"    # wordmark in the white block
    series: str = ""                  # right-aligned series title
    chapters: Sequence[str] = ()      # chapter titles, indexed by Shot.section
    strap_left: str = "REPORTED FACTS  /  ATTRIBUTED CLAIMS  /  OPEN QUESTIONS"
    strap_right: str = ""
    audio_label: str = "ORIGINAL AUDIO"
    muted_label: str = "SOURCE FOOTAGE · MUTED"
    graphic_label: str = "GRAPHIC"

    @property
    def c(self):
        return SUBJECTS.get(self.subject, SUBJECTS["default"])


@dataclass
class Card:
    kicker: str
    big: str
    bullets: Sequence[str] = ()
    credit: str = ""


@dataclass
class Source:
    outlet: str
    programme: str = ""
    date: str = ""
    resolution: str = ""

    def lines(self):
        return [ln for ln in (self.programme, self.date, ("Upload · " + self.resolution) if self.resolution else "") if ln]


@dataclass
class Exhibit:
    """Full-panel number graphic: top line, big figure, note, and a 0-1 progress fraction."""
    top: str
    big: str
    note: str = ""
    frac: float = 1.0


@dataclass
class Shot:
    kind: str = "main"               # "main" (16:9) or "short" (9:16)
    section: int = 0
    card: Card = field(default_factory=lambda: Card("", ""))
    source: Optional[Source] = None  # None = full-panel graphic
    sound: bool = False              # original audio playing (excerpt)
    speaker: Optional[str] = None    # name tab for excerpts
    chyron: Optional[str] = None     # white-bar headline; None = kicker: big (excerpts leave the bar for captions)
    exhibit: Optional[Exhibit] = None
    rows: Sequence[str] = ()         # full-panel list rows (defaults to card.bullets)


# --- Drawing helpers -------------------------------------------------------------
def text(d, s, x, y, kind, size, maxw, color=WHITE, align="left", line=1.18, upper=False):
    """Word-wrapped text; returns the y after the last line."""
    f = font(kind, size); s = s.upper() if upper else s; lines = []
    for para in str(s).split("\n"):
        cur = ""
        for word in para.split():
            test = (cur + " " + word).strip()
            if d.textlength(test, font=f) > maxw and cur:
                lines.append(cur); cur = word
            else:
                cur = test
        lines.append(cur)
    for ln in lines:
        w = d.textlength(ln, font=f)
        xx = x if align == "left" else (x - w if align == "right" else x - w / 2)
        d.text((xx, y), ln, font=f, fill=color); y += size * line
    return y


def _lum(hexcolor):
    r, g, b = (int(hexcolor.lstrip("#")[i:i + 2], 16) / 255 for i in (0, 2, 4))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def on(fill):
    """Text colour that reads on a given fill: white on dark, ink on light accents."""
    return INK if _lum(fill) > 0.45 else WHITE


def tab(d, x, y, s, kind, size, fill, color=None, padx=14, h=None, upper=True):
    """Solid tab with one line of text; returns its right edge."""
    color = color or on(fill)
    f = font(kind, size); t = s.upper() if upper else s; w = d.textlength(t, font=f)
    h = h or round(size * 1.6)
    d.rectangle((x, y, x + w + 2 * padx, y + h), fill=fill)
    d.text((x + padx, y + (h - size) / 2 - size * 0.12), t, font=f, fill=color)
    return x + w + 2 * padx


def fit_size(d, s, kind, start, maxw, floor=14):
    size = start
    while size > floor and d.textlength(s, font=font(kind, size)) > maxw:
        size -= 1
    return size


def default_chyron(card: Card) -> str:
    big = card.big.replace('"', "")
    return f"{card.kicker}: {big}" if len(card.kicker) + len(big) < 44 else big


# --- Plates ----------------------------------------------------------------------------
def render_plate(theme: Theme, shot: Shot, out: Path) -> Tuple[Path, Tuple[int, int, int, int]]:
    """Draw the background plate for one shot. Returns (png path, footage rectangle)."""
    c = theme.c; vert = shot.kind == "short"; L = SHORT_LAYOUT if vert else MAIN_LAYOUT
    W, H = L["W"], L["H"]; px, py, pw, ph = L["px"], L["py"], L["pw"], L["ph"]
    im = Image.new("RGB", (W, H), c["ground"]); d = ImageDraw.Draw(im)
    d.rectangle((0, H * 0.72, W, H), fill=c["ground2"]); d.rectangle((0, 0, W, 4), fill=c["accent_hi"])
    card = shot.card; chapter = theme.chapters[shot.section] if shot.section < len(theme.chapters) else ""
    src = shot.source
    if not vert:
        x = tab(d, 56, 26, theme.channel, "cond", 26, WHITE, c["navy"], h=44)
        if theme.chapters:
            x = tab(d, x + 12, 26, f"{shot.section + 1:02} / {len(theme.chapters):02}", "cond", 22, c["accent"], h=44)
        text(d, chapter, x + 14, 30, "cond", 30, 760, WHITE, upper=True)
        text(d, theme.series, 1864, 34, "cond", 24, 700, c["mute"], align="right", upper=True)
        # sidebar card
        sx, sy, sw, sh = L["sx"], L["sy"], L["sw"], L["sh"]
        d.rectangle((sx, sy, sx + sw, sy + sh), fill=CARD)
        hdr = c["accent2"] if shot.sound else c["accent"]
        d.rectangle((sx, sy, sx + sw, sy + 46), fill=hdr)
        ks = fit_size(d, card.kicker.upper(), "cond", 22, sw - 36)
        text(d, card.kicker, sx + 18, sy + 23 - ks * 0.62, "cond", ks, sw - 36, on(hdr), upper=True)
        big = card.big
        end = text(d, big, sx + 18, sy + 64, "cond", 44 if len(big) < 16 else (34 if len(big) < 24 else 28), sw - 36, c["navy"], upper=True, line=1.05)
        d.rectangle((sx + 18, end + 14, sx + sw - 18, end + 16), fill=RULE); end += 36
        for n, b in enumerate(card.bullets):
            text(d, f"{n + 1:02}", sx + 18, end + 2, "cond", 18, 40, c["accent_hi"])
            end = text(d, b, sx + 52, end, "reg", 21, sw - 70, INK, line=1.22) + 12
        fy = sy + sh - 96
        d.rectangle((sx + 18, fy - 14, sx + sw - 18, fy - 12), fill=RULE)
        text(d, "SOURCE ON SCREEN" if src else "SOURCE RECORD", sx + 18, fy, "bold", 13, sw - 36, GRAY, upper=True)
        yy = fy + 20
        for ln in (src.lines() if src else [card.credit]):
            yy = text(d, ln, sx + 18, yy, "reg", 16, sw - 36, GRAY, line=1.25)
        # tab row + white bar
        ty, by, bh = L["tab_y"], L["bar_y"], L["bar_h"]
        if shot.sound and src:
            x = tab(d, px, ty, shot.speaker or src.outlet, "cond", 24, c["navy"], WHITE, h=44)
            tab(d, x, ty, "  ·  ".join(v for v in (src.programme or src.outlet, src.date) if v), "bold", 18, WHITE, c["navy"], h=44, upper=False)
            w = d.textlength(theme.audio_label.upper(), font=font("cond", 22))
            tab(d, px + pw - w - 28, ty, theme.audio_label, "cond", 22, c["accent2"], h=44)
        elif src:
            x = tab(d, px, ty, theme.muted_label, "cond", 24, c["accent"], h=44)
            tab(d, x, ty, "  ·  ".join(v for v in (src.outlet, src.programme, src.date) if v), "bold", 18, WHITE, c["navy"], h=44, upper=False)
        else:
            x = tab(d, px, ty, f"{theme.channel} {theme.graphic_label}", "cond", 24, c["accent"], h=44)
            if card.credit:
                tab(d, x, ty, card.credit, "bold", 18, WHITE, c["navy"], h=44, upper=False)
        d.rectangle((px, by, px + pw, by + bh), fill=WHITE)
        if not shot.sound:
            text(d, shot.chyron or default_chyron(card), px + 24, by + 16, "cond", 38, pw - 48, INK, upper=True)
        d.rectangle((0, L["strap_y"], W, L["strap_y"] + 32), fill="#060D1F")
        text(d, theme.strap_left, 56, L["strap_y"] + 8, "bold", 15, 1200, c["mute"], upper=True)
        text(d, theme.strap_right, 1864, L["strap_y"] + 8, "bold", 15, 600, c["mute"], align="right", upper=True)
    else:
        tab(d, 56, 96, theme.channel, "cond", 30, WHITE, c["navy"], h=52)
        text(d, theme.series, 56, 172, "cond", 24, 960, c["mute"], upper=True)
        text(d, card.kicker, 56, 222, "cond", 26, 960, c["accent_hi"], upper=True)
        text(d, card.big, 56, 262, "cond", 64 if len(card.big) < 16 else (50 if len(card.big) < 24 else 40), 960, WHITE, upper=True, line=1.02)
        ty, by, bh = L["tab_y"], L["bar_y"], L["bar_h"]
        if shot.sound and src:
            x = tab(d, 0, ty, shot.speaker or src.outlet, "cond", 24, c["navy"], WHITE, h=44)
            tab(d, x, ty, src.outlet, "bold", 18, WHITE, c["navy"], h=44, upper=False)
            w = d.textlength(theme.audio_label.upper(), font=font("cond", 22))
            tab(d, W - w - 28, ty, theme.audio_label, "cond", 22, c["accent2"], h=44)
        elif src:
            x = tab(d, 0, ty, theme.muted_label, "cond", 24, c["accent"], h=44)
            tab(d, x, ty, "  ·  ".join(v for v in (src.outlet, src.date) if v), "bold", 18, WHITE, c["navy"], h=44, upper=False)
        else:
            tab(d, 0, ty, f"{theme.channel} {theme.graphic_label}", "cond", 24, c["accent"], h=44)
        d.rectangle((0, by, W, by + bh), fill=WHITE)  # captions are burned into this bar by the caller
        cy, ch = L["card_y"], L["card_h"]
        d.rectangle((56, cy, 900, cy + ch), fill=CARD); d.rectangle((56, cy, 900, cy + 40), fill=c["accent"])
        text(d, card.kicker, 72, cy + 8, "cond", 20, 800, on(c["accent"]), upper=True)
        end = cy + 60
        for n, b in enumerate(list(card.bullets)[:3]):
            text(d, f"{n + 1:02}", 72, end + 2, "cond", 18, 40, c["accent_hi"])
            end = text(d, b, 108, end, "reg", 24, 770, INK, line=1.2) + 12
        d.rectangle((0, L["strap_y"], W, L["strap_y"] + 36), fill="#060D1F")
        text(d, theme.strap_left, 56, L["strap_y"] + 9, "bold", 15, 960, c["mute"], upper=True)
    # footage frame or full-panel graphic
    if src:
        d.rectangle((px - 2, py - 2, px + pw + 2, py + ph + 2), outline=c["edge"], width=2)
    else:
        d.rectangle((px, py, px + pw, py + ph), fill=c["panel"]); d.rectangle((px, py, px + pw, py + 6), fill=c["accent_hi"])
        if shot.exhibit:
            e = shot.exhibit
            text(d, e.top, px + pw * .06, py + ph * .14, "cond", 30 if vert else 34, pw * .88, c["accent_hi"], upper=True)
            text(d, e.big, px + pw * .06, py + ph * .30, "num", 120 if vert else 176, pw * .88, WHITE, upper=True, line=1.0)
            pr, pg, pb = (int(c["panel"].lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
            track = "#%02X%02X%02X" % tuple(min(255, v + 40) for v in (pr, pg, pb))
            d.rectangle((px + pw * .06, py + ph * .74, px + pw * .94, py + ph * .765), fill=track)
            d.rectangle((px + pw * .06, py + ph * .74, px + pw * (.06 + .88 * max(0.0, min(1.0, e.frac))), py + ph * .765), fill=c["accent_hi"])
            text(d, e.note, px + pw * .06, py + ph * .83, "bold", 18 if vert else 22, pw * .88, c["mute"], upper=True)
        else:
            rows = list(shot.rows or card.bullets)
            text(d, card.kicker, px + pw * .05, py + ph * .09, "cond", 30 if vert else 34, pw * .9, c["accent_hi"], upper=True)
            start = py + ph * .24; rowh = ph * .66 / max(len(rows), 3)
            for n, b in enumerate(rows):
                d.rectangle((px + pw * .05, start + n * rowh, px + pw * .95, start + (n + 1) * rowh - 14), fill=WHITE)
                text(d, f"{n + 1:02}", px + pw * .075, start + n * rowh + 14, "cond", 26 if vert else 30, pw * .08, c["accent_hi"])
                text(d, b, px + pw * .15, start + n * rowh + 12, "cond", 30 if vert else 40, pw * .77, INK, upper=True)
    out = Path(out); out.parent.mkdir(parents=True, exist_ok=True); im.save(out)
    return out, (px, py, pw, ph)


# --- Captions and overlays -----------------------------------------------------------------
def ass_header(kind: str, theme: Theme) -> str:
    """ASS script header with Quote (excerpt) and Narr (narration) styles for the white bar."""
    L = SHORT_LAYOUT if kind == "short" else MAIN_LAYOUT
    accent = theme.c["accent"].lstrip("#"); bgr = accent[4:6] + accent[2:4] + accent[0:2]
    return ("[Script Info]\nScriptType: v4.00+\nPlayResX: %d\nPlayResY: %d\nWrapStyle: 0\nScaledBorderAndShadow: yes\n\n"
            "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
            "Style: Quote,Roboto,%d,&H00181410,&H00%s,&H00FFFFFF,&H00FFFFFF,-1,0,0,0,100,100,0,0,1,0,0,7,%d,%d,0,1\n"
            "Style: Narr,Roboto,%d,&H00181410,&H00%s,&H00FFFFFF,&H00FFFFFF,-1,0,0,0,100,100,0,0,1,0,0,7,%d,%d,0,1\n\n"
            "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n") % (
        L["W"], L["H"], 30, bgr, L["cap_x"], (L["W"] - (L["px"] + L["pw"]) + 24) if kind != "short" else 150,
        36, bgr, L["cap_x"], (L["W"] - (L["px"] + L["pw"]) + 24) if kind != "short" else 150)


def caption_tag(kind: str) -> str:
    """Override tag placing caption text in the white bar, vertically centred, left-aligned."""
    L = SHORT_LAYOUT if kind == "short" else MAIN_LAYOUT
    return "{\\an4\\pos(%d,%d)\\q0}" % (L["cap_x"], L["cap_y"])


def progress_bar(kind: str, theme: Theme, a: float, b: float, stamp) -> str:
    """ASS event drawing a progress line along the bottom edge of the footage panel."""
    L = SHORT_LAYOUT if kind == "short" else MAIN_LAYOUT
    x, y, w = L["px"], L["py"] + L["ph"], L["pw"]
    accent = theme.c["accent_hi"].lstrip("#"); bgr = accent[4:6] + accent[2:4] + accent[0:2]
    return (f"Dialogue: 5,{stamp(a)},{stamp(b)},Quote,,0,0,0,,{{\\an7\\pos({x},{y})\\p1\\bord0\\shad0\\1c&H{bgr}&"
            f"\\clip({x},{y},{x},{y + 4})\\t(0,{round((b - a) * 1000)},\\clip({x},{y},{x + w},{y + 4}))}}m 0 0 l {w} 0 {w} 4 0 4{{\\p0}}")


def cover(theme: Theme, frame: Image.Image, big: str, line2: str, headline: str, tags: str, note: str, out: Path, vertical=False) -> Path:
    """Thumbnail: a real frame plus a headline block in the house style."""
    c = theme.c
    if not vertical:
        im = Image.new("RGB", (1280, 720), c["ground"]); d = ImageDraw.Draw(im)
        fw, fh = frame.size; crop = frame.crop((int(fw * 0.27), 0, int(fw * 0.27) + int(fh * 0.68 * 1.11), int(fh * 0.68))).resize((800, 720))
        im.paste(crop, (0, 0)); d.rectangle((790, 0, 1280, 720), fill=c["ground"]); d.rectangle((790, 0, 796, 720), fill=c["accent_hi"]); d.rectangle((0, 0, 1280, 6), fill=c["accent_hi"])
        tab(d, 826, 36, theme.channel, "cond", 24, WHITE, c["navy"], h=42)
        text(d, big, 826, 108, "num", 150, 430, WHITE, upper=True, line=1.0)
        d.rectangle((826, 270, 1244, 336), fill=WHITE); text(d, line2, 842, 282, "cond", fit_size(d, line2.upper(), "cond", 44, 386), 400, INK, upper=True)
        text(d, headline, 826, 362, "cond", 78, 430, WHITE, upper=True, line=0.98)
        tab(d, 826, 560, tags, "cond", 22, c["accent"], h=40)
        text(d, note, 826, 620, "bold", 18, 440, c["mute"], upper=True)
    else:
        im = Image.new("RGB", (1080, 1920), c["ground"]); d = ImageDraw.Draw(im)
        fw, fh = frame.size; crop = frame.crop((int(fw * 0.28), 0, int(fw * 0.28) + int(fh * 0.68 * 1.16), int(fh * 0.68))).resize((1080, 930))
        im.paste(crop, (0, 420)); d.rectangle((0, 0, 1080, 6), fill=c["accent_hi"])
        tab(d, 56, 80, theme.channel, "cond", 30, WHITE, c["navy"], h=52)
        text(d, big, 56, 150, "num", 190, 960, WHITE, upper=True, line=1.0)
        d.rectangle((0, 1350, 1080, 1440), fill=WHITE); text(d, line2, 56, 1362, "cond", fit_size(d, line2.upper(), "cond", 60, 960), 960, INK, upper=True)
        text(d, headline, 56, 1470, "cond", 84, 960, WHITE, upper=True)
        tab(d, 56, 1590, tags, "cond", 26, c["accent"], h=48)
    out = Path(out); im.save(out, quality=92); return out


# --- Demo ------------------------------------------------------------------------------------
DEMO = {
    "politics": dict(channel="CIVIC CONTEXT", series="THE $5,000 PROMISE: THE CRITICS' CASE", chapters=["THE PROMISE", "THE MATH", "WHO DECIDES?"],
                     card=Card("THE ARITHMETIC", "$1.3 TRILLION", ["≈ 269 million adults (CBS figure)", "× $5,000 each", "Before administration costs"], "CBS, NBC, MS NOW and PBS estimates"),
                     source=Source("CBS NEWS", "CBS Mornings", "September 10, 2026", "1920×1080"), speaker="ED O'KEEFE, CBS NEWS",
                     exhibit=Exhibit("269 MILLION × $5,000", "$1.3 TRILLION", "ILLUSTRATIVE, BEFORE ADMINISTRATION COSTS", 1.0), strap_right="RESEARCH CUTOFF SEPTEMBER 12, 2026"),
    "science": dict(channel="CIVIC CONTEXT", series="ROGUE WAVES: THE WALL THAT SHOULDN'T EXIST", chapters=["THE DRAUPNER WAVE", "THE PHYSICS", "WHAT SHIPS SEE"],
                    card=Card("THE MEASUREMENT", "25.6 METRES", ["Draupner platform, North Sea, 1995", "First instrument record of a rogue wave", "Twice the significant wave height"], "Statoil laser gauge record"),
                    source=Source("BBC", "Horizon", "March 3, 2026", "1920×1080"), speaker="DR. JOHANNES GEMMRICH, OCEANOGRAPHER",
                    exhibit=Exhibit("SIGNIFICANT WAVE HEIGHT × 2.2", "25.6 M", "DRAUPNER, JANUARY 1, 1995", 0.92), strap_right="SOURCES ON SCREEN · MEASUREMENTS AS PUBLISHED"),
    "gaming": dict(channel="CIVIC CONTEXT", series="ZELDA: A LINK TO THE PAST — BEFORE YOU PLAY", chapters=["THE MAGIC CAPE", "THE PEGASUS BOOTS", "THE SWORD SKIP"],
                   card=Card("THE TRICK", "12 SECONDS", ["Dash into the wall on frame 3", "Requires Pegasus Boots", "Any% and 100% categories"], "Verified on Switch Online, v1.0"),
                   source=Source("GAMEPLAY", "Captured on Switch Online", "September 12, 2026", "1920×1080"), speaker="ORIGINAL GAME AUDIO",
                   exhibit=Exhibit("ROUTE SAVING", "12 SECONDS", "PER LOOP · VERIFIED OVER 10 ATTEMPTS", 0.6), strap_right="GAME VERSION 1.0 · CATEGORY RULES APPLY"),
    "sports": dict(channel="CIVIC CONTEXT", series="THE 4TH QUARTER COLLAPSE", chapters=["THE LEAD", "THE TURNOVERS", "THE LAST DRIVE"],
                   card=Card("THE SWING", "17 POINTS", ["Three turnovers in 6:12", "Two on the same coverage", "Largest blown lead this season"], "Official play-by-play"),
                   source=Source("ESPN", "Monday Night Football", "September 8, 2026", "1920×1080"), speaker="HEAD COACH, POSTGAME",
                   exhibit=Exhibit("LEAD AT 12:00 · FINAL MARGIN", "17 → −3", "THREE TURNOVERS IN SIX MINUTES", 0.85), strap_right="STATS AS PUBLISHED BY THE LEAGUE"),
}


def demo(out_dir: Path, footage: Optional[dict] = None):
    """Render sample plates for each subject; `footage` maps subject -> image path to paste into the panel."""
    from PIL import Image as _I
    out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True); made = []
    for subject, cfg in DEMO.items():
        theme = Theme(subject=subject, channel=cfg["channel"], series=cfg["series"], chapters=cfg["chapters"], strap_right=cfg["strap_right"])
        shots = {"excerpt": Shot("main", 1, cfg["card"], cfg["source"], True, cfg["speaker"]),
                 "broll": Shot("main", 0, cfg["card"], cfg["source"], False),
                 "exhibit": Shot("main", 1, cfg["card"], None, False, exhibit=cfg["exhibit"]),
                 "short": Shot("short", 0, cfg["card"], cfg["source"], False)}
        for name, shot in shots.items():
            png, (x, y, w, h) = render_plate(theme, shot, out_dir / f"{subject}_{name}.png")
            if shot.source and footage and footage.get(subject):
                im = _I.open(png).convert("RGB"); fr = _I.open(footage[subject]).convert("RGB")
                fw, fh = fr.size; scale = min(w / fw, h / fh); fr = fr.resize((round(fw * scale), round(fh * scale)))
                im.paste(fr, (x + (w - fr.width) // 2, y + (h - fr.height) // 2)); im.save(png)
            made.append(png)
    return made


if __name__ == "__main__":
    import argparse, json
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--demo", metavar="OUT_DIR", help="render sample plates for the four subjects")
    ap.add_argument("--footage", help="JSON mapping subject -> image path pasted into the demo panels")
    a = ap.parse_args()
    if a.demo:
        foot = json.loads(Path(a.footage).read_text(encoding="utf-8")) if a.footage else None
        for p in demo(Path(a.demo), foot):
            print(p)
