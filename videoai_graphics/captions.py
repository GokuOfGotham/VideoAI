"""Dependency-free caption grouping and self-contained ASS event generation.

``max_chars`` is a per-line ceiling; captions use at most two lines. ``y`` is
an optional normalized anchor. Event times are centisecond-safe for ASS;
group times and SRT retain millisecond precision. All times are seconds.
"""

import math
import re
import unicodedata
from decimal import Decimal, ROUND_FLOOR, ROUND_HALF_UP


_ACCENTS = {
    "political": "#EF4444", "space": "#38BDF8",
    "gaming": "#B7F34A", "reaction": "#B79CFF",
}
_OPTIONS = {
    "style", "font_name", "font_size", "words_per_caption", "max_chars",
    "position", "y", "uppercase", "color", "active_color", "outline_color",
}
_PUNCTUATION = re.compile(r"[.!?,;:\u2026][\"'\u2019\u201d)]*$")
_PAUSE = 0.45
_HOLD = 0.12


def _number(value, name, minimum=None, maximum=None):
    if isinstance(value, bool) or not isinstance(value, (float, int)):
        raise ValueError(f"{name} must be a finite number")
    try:
        result = float(value)
    except (OverflowError, ValueError):
        raise ValueError(f"{name} must be a finite number") from None
    if not math.isfinite(result):
        raise ValueError(f"{name} must be a finite number")
    if minimum is not None and result < minimum:
        raise ValueError(f"{name} must be at least {minimum}")
    if maximum is not None and result > maximum:
        raise ValueError(f"{name} must be at most {maximum}")
    return result


def _integer(value, name, minimum, maximum):
    result = _number(value, name, minimum, maximum)
    if result != int(result):
        raise ValueError(f"{name} must be an integer")
    return int(result)


def _ticks(seconds, rate):
    return int((Decimal(str(seconds)) * rate).to_integral_value(rounding=ROUND_HALF_UP))


def _floor_ticks(seconds, rate):
    return int((Decimal(str(seconds)) * rate).to_integral_value(rounding=ROUND_FLOOR))


def _srt_timestamp(seconds):
    ticks = _ticks(seconds, 1000)
    hours, ticks = divmod(ticks, 3600000)
    minutes, ticks = divmod(ticks, 60000)
    secs, millis = divmod(ticks, 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{millis:03}"


def _ass_text(value):
    # A doubled backslash is not reliably literal in libass. Fullwidth glyphs
    # preserve visible punctuation without permitting override or drawing tags.
    return value.replace("\\", "\uff3c").replace("{", "\uff5b").replace("}", "\uff5d")


def _color(value, name):
    if not isinstance(value, str) or not re.fullmatch(r"#[0-9A-Fa-f]{6}", value):
        raise ValueError(f"{name} must be a #RRGGBB color")
    return "&H" + value[5:7].upper() + value[3:5].upper() + value[1:3].upper() + "&"


def _units(value):
    """Conservative text width estimate in ems, requiring no font libraries."""
    total = 0.0
    for char in value:
        if unicodedata.combining(char):
            continue
        if unicodedata.east_asian_width(char) in ("W", "F"):
            total += 1.05
        elif char.isspace():
            total += 0.34
        elif char in "ilI.,'`!:;|":
            total += 0.33
        elif char in "MW@%&":
            total += 0.92
        elif char.isupper():
            total += 0.70
        else:
            total += 0.59
    return total


def _layout(words, font_size, available_width, max_chars):
    """Return token-to-line mapping, or None when the phrase needs >2 lines."""
    lines = [[]]
    line_text = ""
    for index, word in enumerate(words):
        candidate = (line_text + " " + word).strip()
        if line_text and (len(candidate) > max_chars or _units(candidate) * font_size > available_width):
            lines.append([])
            line_text = ""
        if len(lines) > 2:
            return None
        lines[-1].append((index, word))
        line_text = (line_text + " " + word).strip()
        if len(word) > max_chars or _units(word) * font_size > available_width:
            # Only a single unbroken token is eligible for character wrapping.
            if len(words) != 1:
                return None
            midpoint = max(1, len(word) // 2)
            halves = (word[:midpoint], word[midpoint:])
            if any(len(part) > max_chars for part in halves):
                return None
            return [[(0, halves[0])], [(0, halves[1])]]
    return lines


def _normalize_words(words, uppercase, duration=None):
    if not isinstance(words, (list, tuple)):
        raise ValueError("words must be a list of word/start/end objects")
    result = []
    for index, item in enumerate(words):
        if not isinstance(item, dict) or not all(key in item for key in ("word", "start", "end")):
            raise ValueError(f"words[{index}] must contain word, start, and end")
        value = item["word"]
        if not isinstance(value, str):
            raise ValueError(f"words[{index}].word must be text")
        # Normalize whitespace and strip C0/C1 controls before any output.
        value = " ".join("".join(char if char.isspace() or unicodedata.category(char) != "Cc" else "" for char in value).split())
        if not value:
            raise ValueError(f"words[{index}].word must not be empty")
        start = _number(item["start"], f"words[{index}].start", 0)
        end = _number(item["end"], f"words[{index}].end", 0)
        if end <= start:
            raise ValueError(f"words[{index}].end must be after start")
        if duration is not None:
            if start >= duration or end > duration + 0.000001:
                raise ValueError(f"words[{index}] is outside the video duration")
            end = min(end, duration)
        result.append({"word": value.upper() if uppercase else value, "start": start, "end": end})
    result.sort(key=lambda item: item["start"])  # Stable for equal timestamps.
    for index, item in enumerate(result[:-1]):
        item["end"] = min(item["end"], result[index + 1]["start"])
    return result


def _join_layout(layout, decorate):
    return r"\N".join(" ".join(decorate(index, token) for index, token in line) for line in layout)


def build_captions(words, width, height, preset="gaming", options=None, *, duration=None):
    """Build caption ASS events, SRT, and phrase metadata from timed words.

    Styles: ``clean`` shows a phrase, ``highlight`` colors its active word,
    and ``karaoke`` progressively fills words using ASS ``\\kf`` tags.
    ``duration`` optionally caps caption holds at the video boundary and
    rejects words outside it. Invalid timestamps and unsafe options raise
    ValueError. Exported end times never round beyond a supplied duration.
    """
    width = _integer(width, "width", 160, 16384)
    height = _integer(height, "height", 160, 16384)
    if duration is not None:
        duration = _number(duration, "duration", 0)
        if duration <= 0:
            raise ValueError("duration must be greater than zero")
    if not isinstance(preset, str) or preset not in _ACCENTS:
        raise ValueError("preset must be political, space, gaming, or reaction")
    if options is None:
        options = {}
    if not isinstance(options, dict):
        raise ValueError("options must be an object")
    unknown = set(options) - _OPTIONS
    if unknown:
        raise ValueError("Unsupported caption option: " + ", ".join(sorted(map(str, unknown))))
    style = options.get("style", "clean" if preset in ("political", "space") else "highlight")
    if style not in ("clean", "highlight", "karaoke"):
        raise ValueError("style must be clean, highlight, or karaoke")
    font_name = options.get("font_name", "Arial")
    if not isinstance(font_name, str) or not re.fullmatch(r"[\w][\w .-]{0,79}", font_name, re.UNICODE):
        raise ValueError("font_name contains unsupported characters")
    font_size = _number(options.get("font_size", max(18, min(80, height * 0.052, width * 0.08))), "font_size", 12, min(width, height) * 0.25)
    max_words = _integer(options.get("words_per_caption", 6 if style == "clean" else 5), "words_per_caption", 1, 32)
    max_chars = _integer(options.get("max_chars", 32), "max_chars", 4, 120)
    position = options.get("position", "bottom")
    if position not in ("bottom", "center", "top"):
        raise ValueError("position must be bottom, center, or top")
    default_y = {"bottom": 0.86 if height > width else 0.88, "center": 0.5, "top": 0.16}[position]
    anchor_y = _number(options.get("y", default_y), "y", 0.05, 0.95)
    uppercase = options.get("uppercase", False)
    if not isinstance(uppercase, bool):
        raise ValueError("uppercase must be true or false")
    base_color = _color(options.get("color", "#FFFFFF"), "color")
    active_color = _color(options.get("active_color", _ACCENTS[preset]), "active_color")
    outline_color = _color(options.get("outline_color", "#101820"), "outline_color")
    timed_words = _normalize_words(words, uppercase, duration)
    available_width = width * 0.86
    phrase_words = []
    current = []
    for item in timed_words:
        candidate = current + [item]
        should_break = current and (
            len(candidate) > max_words
            or item["start"] - current[-1]["end"] > _PAUSE
            or (bool(_PUNCTUATION.search(current[-1]["word"])) and _ticks(item["start"], 100) > _ticks(current[0]["start"], 100))
            or _layout([entry["word"] for entry in candidate], font_size, available_width, max_chars) is None
        )
        if should_break:
            phrase_words.append(current)
            current = []
        current.append(item)
    if current:
        phrase_words.append(current)

    events = []
    groups = []
    srt_entries = []
    previous_end_cs = 0
    for phrase_index, phrase in enumerate(phrase_words):
        tokens = [item["word"] for item in phrase]
        layout = _layout(tokens, font_size, available_width, max_chars)
        if layout is None:
            raise ValueError("A word exceeds the two-line character limit; increase max_chars or split the input word")
        # A long single token can require a smaller font after its line split.
        widest = max(_units(" ".join(token for _, token in line)) for line in layout)
        actual_size = min(font_size, available_width / max(widest, 1))
        if actual_size < 12:
            raise ValueError("Caption cannot fit safely at a readable font size")
        start = phrase[0]["start"]
        end = max(item["end"] for item in phrase) + _HOLD
        if duration is not None:
            end = min(end, duration)
        if phrase_index + 1 < len(phrase_words):
            end = min(end, phrase_words[phrase_index + 1][0]["start"])
        # Keep word order and phrase events disjoint even when input word
        # intervals overlap or several words round to the same centisecond.
        start_cs = max(previous_end_cs, _ticks(start, 100))
        end_cs = _ticks(end, 100)
        if duration is not None:
            end_cs = min(end_cs, _floor_ticks(duration, 100))
        if end_cs <= start_cs:
            raise ValueError("Caption phrase is too short to represent at ASS centisecond precision")
        previous_end_cs = end_cs
        groups.append({"start": start, "end": end, "text": " ".join(tokens)})
        srt_text = "\n".join(" ".join(token for _, token in line) for line in layout)
        srt_end = min(end, _floor_ticks(duration, 1000) / 1000) if duration is not None else end
        srt_entries.append(f"{len(groups)}\n{_srt_timestamp(start)} --> {_srt_timestamp(srt_end)}\n{srt_text}\n")
        alignment = {"bottom": 2, "center": 5, "top": 8}[position]
        primary = active_color if style == "karaoke" else base_color
        secondary = base_color if style == "karaoke" else active_color
        prefix = (
            "{" + rf"\an{alignment}\pos({width / 2:.1f},{height * anchor_y:.1f})"
            + rf"\fn{font_name}\fs{actual_size:.2f}\b1\i0\u0\s0\fscx100\fscy100\fsp0\frz0"
            + rf"\1c{primary}\2c{secondary}\3c{outline_color}\4c&H000000&"
            + rf"\alpha&H00&\bord{max(1.5, actual_size * 0.055):.2f}\shad{max(1, actual_size * 0.035):.2f}\blur0.3\q2"
            + "}"
        )
        if style == "clean":
            text = prefix + _join_layout(layout, lambda index, token: _ass_text(token))
            events.append({"layer": 20, "start": start_cs / 100, "end": end_cs / 100, "text": text})
        elif style == "highlight":
            # The phrase remains visible throughout; the previous word stays
            # highlighted briefly during natural spaces between spoken words.
            for index, item in enumerate(phrase):
                word_start_cs = start_cs if index == 0 else max(start_cs, _ticks(item["start"], 100))
                word_end_cs = min(end_cs, _ticks(phrase[index + 1]["start"], 100)) if index + 1 < len(phrase) else end_cs
                if word_end_cs <= word_start_cs:
                    continue
                text = prefix + _join_layout(layout, lambda token_index, token: "{" + r"\1c" + (active_color if token_index == index else base_color) + "}" + _ass_text(token))
                events.append({"layer": 20, "start": word_start_cs / 100, "end": word_end_cs / 100, "text": text})
        else:
            # ASS karaoke durations are relative to the event. Distribute each
            # word's interval across its fragments when a long token wraps.
            fragments = {}
            for line in layout:
                for index, token in line:
                    fragments.setdefault(index, []).append(token)
            counts = {index: 0 for index in fragments}

            def karaoke(index, token):
                word_start_cs = start_cs if index == 0 else max(start_cs, _ticks(phrase[index]["start"], 100))
                word_end_cs = min(end_cs, _ticks(phrase[index + 1]["start"], 100)) if index + 1 < len(phrase) else end_cs
                duration = max(0, word_end_cs - word_start_cs)
                prior_chars = counts[index]
                counts[index] += len(token)
                total_chars = sum(len(part) for part in fragments[index])
                fragment_duration = round(duration * counts[index] / total_chars) - round(duration * prior_chars / total_chars)
                return "{" + rf"\kf{fragment_duration}" + "}" + _ass_text(token)

            text = prefix + _join_layout(layout, karaoke)
            events.append({"layer": 20, "start": start_cs / 100, "end": end_cs / 100, "text": text})
    return {"events": events, "srt": "\n".join(srt_entries), "groups": groups}
