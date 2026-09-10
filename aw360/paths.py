"""Shared path configuration for the AW360 director.

Every location resolves relative to the project root this package lives in, so
a clone works wherever it lands, with per-directory overrides available through
the environment. Mirrors the configuration approach the rest of the toolkit
already uses via MEDIA_ROOT / OUTPUT_DIR.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _resolve(env_name: str, *default_parts: str) -> Path:
    """Returns the configured path, or one derived from the project root."""
    override = os.getenv(env_name)
    if override:
        return Path(override).expanduser()
    return PROJECT_ROOT.joinpath(*default_parts)


ASSETS_DIR = _resolve("ASSETS_DIR", "assets")
CACHE_DIR = _resolve("AW360_CACHE_DIR", "assets", "aw360_cache")
FONT_DIR = _resolve("AW360_FONT_DIR", "assets", "fonts")
EPIDEMIC_MUSIC_DIR = _resolve("EPIDEMIC_MUSIC_DIR", "assets", "epidemic_sound")

# The toolkit-wide OUTPUT_DIR holds every pipeline's renders; AW360 keeps its
# own subfolder inside it unless pointed somewhere else outright.
OUTPUT_DIR = (
    Path(os.getenv("AW360_OUTPUT_DIR")).expanduser()
    if os.getenv("AW360_OUTPUT_DIR")
    else _resolve("OUTPUT_DIR", "output") / "aw360"
)


def ensure_dirs() -> None:
    """Creates every AW360 working directory that does not exist yet."""
    for directory in (ASSETS_DIR, CACHE_DIR, FONT_DIR, EPIDEMIC_MUSIC_DIR, OUTPUT_DIR):
        directory.mkdir(parents=True, exist_ok=True)
