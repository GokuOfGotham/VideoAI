"""Director tools: know the footage, draft from its best lines, check the story, review the cut.

- ``scene_index``  — a per-source scene log (cuts, thumbnails, who is on screen, what is said, by whom)
                     so shots are chosen by meaning instead of by guessing a timecode.
- ``excerpts``     — ranked candidate excerpts (complete lines on measured word boundaries) so the
                     script is written around the footage's best lines, not the other way round.
- ``story``        — the story spine (question, claim, evidence, turn, re-hooks, open loops, payoff,
                     button) and deterministic checks the policy runs on any plan that declares one.
- ``review``       — the director's review: a punch list against the scene log (unsupported claims,
                     dead stretches, repeats, weak chapter titles, ending versus title).

Nothing here changes how a video renders; it changes what gets planned. Network calls happen only
in ``scene_index`` (transcription, vision) and ``review`` (one chat call), never at import.
"""
from . import story  # noqa: F401  (pure; safe to import anywhere)

__all__ = ["story"]
