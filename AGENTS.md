# VideoAI project preferences

## Shared production policy — applies to every AI

Before planning, writing, editing or rendering, read [PRODUCTION_RULES.md](PRODUCTION_RULES.md) and load [videoai_policy/policy.json](videoai_policy/policy.json). Use that single source of truth regardless of the AI provider. Pass `python policy_tool.py prompt` to any model working outside this project context.

Every production needs a concrete `production_review` in its script/config: immediate hook, meaningful first payoff within fifteen seconds, a pacing review, the correct audio mode, and standalone treatment for Shorts. Validate with `python policy_tool.py check <plan.json>` before final production, including custom FFmpeg and one-off workflows. Run the actual visual/audio QA described in the policy; a plan check alone is not final-media approval.

Gameplay highlights default to original game audio. Narrated documentaries and lore use the approved Cedar preset below. Treat analytics percentages as benchmarks, never algorithmic guarantees; do not diagnose a six-view sample as proof of clickbait or a precise retention cliff. An explicit user request can override a default; record the existing request without asking again. Do not fabricate exceptions or silently substitute another voice or an unrelated canned script after an API failure.

For civic, election and policy explainers, use **politics mode** (`production_review.mode = "politics"`, the POLITICS MODE rules in the policy and the Politics mode section of PRODUCTION_RULES.md): broadcast footage from named outlets, verified word-boundary excerpts with speakers on screen, no replayed ranges, captions re-timed from the audio, a fact-check table and a source manifest. `python policy_tool.py prompt --mode politics` briefs any other model. Reference build: `create_5000_promise_v2.py`.

For gaming work, apply the canonical GAMING rules and the Gaming content section of PRODUCTION_RULES.md before choosing the format. Record the viewer question/objective, evidence and format in the production review; distinguish narrated essays and guides from original-audio highlights. Honor explicit user format choices.

## Default narration — user approved

For future videos, use `APPROVED_VOICE_PRESET.json`: OpenAI Cedar with gpt-4o-mini-tts and the exact saved conversational direction. The user approved the Voice_V3 Batman vs Predator delivery on 2026-09-11 and requested it going forward. This is the default unless the user requests another voice.

Preserve natural phrasing. Do not slow down, pitch-shift, or stretch finished speech to fill the edit. Prefer rewriting or regenerating a line; add brief pauses only at punctuation, never arbitrarily inside a phrase. Keep narration clear over music and retime captions to the final recording. Use the approved reference files for comparison.

Some legacy scripts hardcode Onyx, older models, or other providers. Override those legacy defaults with this preset when producing new videos; do not assume their defaults match the user's preference.
