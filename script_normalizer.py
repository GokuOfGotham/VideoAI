"""Master Audio Engineer & Voiceover Director Script Normalizer for VideoAI.

Pre-processes text scripts for TTS generation to guarantee human-like,
artifact-free narration, precise pacing, and clean phonetic enunciation.
"""

import re
from typing import List


def normalize_script_for_tts(text: str) -> str:
    """Applies Master Voiceover Director rules to normalize text for TTS APIs."""
    if not text:
        return ""

    s = text

    # 1. Remove exclamation points to prevent TTS yelling/distortion
    s = s.replace("!", ".")

    # 2. Currency Normalization ($45.67 -> forty-five dollars and sixty-seven cents)
    s = re.sub(
        r"\$(\d+)\.(\d{2})\b",
        lambda m: f"{_number_to_words(int(m.group(1)))} dollars and {_number_to_words(int(m.group(2)))} cents",
        s
    )
    s = re.sub(
        r"\$(\d+)\b",
        lambda m: f"{_number_to_words(int(m.group(1)))} dollars",
        s
    )

    # 3. Decades Normalization (1990s -> nineteen nineties, 2020s -> twenty twenties)
    s = re.sub(r"\b19(\d0)s\b", r"nineteen \1s", s)
    s = re.sub(r"\b20(\d0)s\b", r"twenty \1s", s)

    # 4. Number Normalization (standalone digits)
    s = re.sub(r"\b\d+\b", lambda m: _number_to_words(int(m.group(0))), s)

    # 5. Acronym & Jargon Normalization
    acronym_map = {
        r"\bAWS\b": "A-W-S",
        r"\bAPI\b": "A-P-I",
        r"\bAI\b": "A-I",
        r"\bSQLite\b": "sequel-ite",
        r"\bSQL\b": "sequel",
        r"\bUI\b": "U-I",
        r"\bUX\b": "U-X",
        r"\bTTS\b": "T-T-S",
        r"\bFFmpeg\b": "ef-ef-mpeg"
    }
    for pattern, replacement in acronym_map.items():
        s = re.sub(pattern, replacement, s)

    # 6. Conversational Phrasing Transitions & Contractions
    formal_phrases = {
        r"\bFurthermore,\b": "Plus,",
        r"\bTherefore,\b": "So,",
        r"\bHowever,\b": "But,",
        r"\bAdditionally,\b": "Also,",
        r"\bdo not\b": "don't",
        r"\bcannot\b": "can't",
        r"\bwill not\b": "won't",
        r"\bI will\b": "I'll",
        r"\bthey are\b": "they're",
        r"\bwe are\b": "we're",
        r"\bit is\b": "it's"
    }
    for pattern, replacement in formal_phrases.items():
        s = re.sub(pattern, replacement, s, flags=re.IGNORECASE)

    # 7. Pacing Control Punctuation Normalization
    s = re.sub(r"\s*--\s*", " — ", s)
    s = re.sub(r"\s*\.\.\.\s*", "... ", s)
    s = re.sub(r"\s+", " ", s).strip()

    return s


def chunk_script_text(text: str, max_chars: int = 650) -> List[str]:
    """Splits script into 500-800 character chunks to prevent TTS emotional drift."""
    if len(text) <= max_chars:
        return [text]

    sentences = re.split(r"(?<=[.!?—])\s+", text)
    chunks = []
    current_chunk = []
    current_len = 0

    for sentence in sentences:
        if current_len + len(sentence) > max_chars and current_chunk:
            chunks.append(" ".join(current_chunk))
            current_chunk = [sentence]
            current_len = len(sentence)
        else:
            current_chunk.append(sentence)
            current_len += len(sentence) + 1

    if current_chunk:
        chunks.append(" ".join(current_chunk))

    return chunks


def _number_to_words(n: int) -> str:
    """Helper converting numbers (0-9999) into spoken words."""
    if n == 0:
        return "zero"

    units = [
        "", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine",
        "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen",
        "seventeen", "eighteen", "nineteen"
    ]
    tens = [
        "", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"
    ]

    if n < 20:
        return units[n]
    if n < 100:
        return tens[n // 10] + ("-" + units[n % 10] if n % 10 != 0 else "")
    if n < 1000:
        return units[n // 100] + " hundred" + (" and " + _number_to_words(n % 100) if n % 100 != 0 else "")
    if n < 10000:
        return _number_to_words(n // 1000) + " thousand" + (" " + _number_to_words(n % 1000) if n % 1000 != 0 else "")

    return str(n)


if __name__ == "__main__":
    test_raw = "Furthermore, in the 1990s, AWS cost $45.67! Therefore, we do not use SQLite in 2026."
    print("RAW:", test_raw)
    print("NORMALIZED:", normalize_script_for_tts(test_raw))
