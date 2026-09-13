# VideoAI production rules

The canonical policy is [videoai_policy/policy.json](videoai_policy/policy.json). It contains the user-approved editing, audio, visual, factual and analytics defaults. The same policy is loaded for every supported script provider. Do not maintain separate copies of the rules inside model-specific prompts.

## Every production

Start with the promised conflict or action at second zero; deliver a meaningful first payoff within fifteen seconds. Remove loading, redundant travel, repetition and empty pauses while retaining useful setup and tension. Gameplay highlights default to original game audio. Documentary and lore narration default to the exact saved Cedar preset. Shorts stand alone unless a trailer is specifically requested. Keep footage sharp, sources honest, speech natural, and final checks specific to what was actually inspected.

CTR, APV, completion and stayed-to-watch figures are working benchmarks, not algorithm switches. Six views cannot diagnose a thumbnail or recommendation failure. An average view duration does not locate a retention cliff. Use the retention curve, sample size and traffic sources before deciding a revision.

## Gaming content

The gaming rules in the canonical policy apply to every provider. Prefer focused essays and practical guides when selecting a long-form concept; use complete gameplay moments or insights for Shorts. Honor an existing user choice of format. Each video needs a specific viewer question, objective or payoff beyond showing a game being played.

- Essays: one question and thesis, supported by inspected gameplay and verified research. Use Cedar for analysis and original game audio for key moments.
- Mechanics, glitch and speedrun guides: show the result immediately, then provide reproducible steps, prerequisites, game version and category rules. Preserve uninterrupted evidence when necessary.
- Walkthroughs: useful objectives and accurate final-export chapters; cut downtime while retaining navigation and required steps. Verify the scope of a 100% claim.
- Shorts: one complete moment or insight with the promised payoff. Original game audio for pure highlights; Cedar for narrated analysis. Standalone unless a trailer is requested.

Record the chosen format, viewer question/objective, supporting footage or sources and relevant guide/chapter plan in `production_review.pacing_review`. For existing schema/audio defaults, use `lore` for narrated gaming essays, `documentary` for narrated instructional guides, and `gameplay` for original-audio highlights or unnarrated guides. This avoids treating an analytical essay as a silent gameplay highlight.

These are editorial defaults delivered in the common model prompt. Automated checks do not establish the strength of a thesis, tutorial reproducibility or chapter accuracy; inspect the actual script and export. Test formats against comparable channel results. The [200 million video-essay views in 2024](https://blog.youtube/culture-and-trends/the-joy-of-video-essays/) covers all subjects, not gaming alone, and does not prove that Let's Plays are obsolete.

## Using another AI

Have the assistant read this file, AGENTS.md and the canonical policy before planning. AGENTS.md, CLAUDE.md and GEMINI.md point here. An assistant operating outside this folder can receive the shared prompt:

```powershell
python policy_tool.py prompt --content-type lore --format long
python policy_tool.py prompt --content-type gameplay --format short
```

Add the emitted `production_review` object to the script/config. Fill it with real descriptions and planned times; blank templates deliberately fail. The hook must describe the actual opening; the payoff must name the first delivered answer/action/evidence. `pacing_review` records what was removed and why any deliberate pauses or setup remain.

```powershell
python policy_tool.py template --content-type documentary --format long
python policy_tool.py check production.json --duration 540
```

The check exits nonzero for missing/incomplete review, delayed hook or payoff, conflicting audio mode, promotional standalone Shorts, identified downtime without a reason, and obvious greeting/forced-pause script patterns. Explicit user exceptions go in `overrides` under `hook`, `payoff`, `pacing`, `audio` or `standalone`, each with `reason` and the actual `user_request`. This records an existing choice; it does not require a new approval conversation. Do not invent a user exception to get a pass.

## Enforcement coverage

- `script_generator.py`: shared prompt for OpenAI, Gemini and DeepSeek; validate returned scripts; fail when all providers fail instead of substituting unrelated canned narration.
- `pipeline.py` and `main.py`: use that generator; natural Cedar defaults. `main.py` narration uses the common synthesizer instead of the old dramatic-pause/alternate-voice chain.
- AW360: shared script/research instructions and script validation, with no unrelated canned fallback. Its normal narration path defaults to Cedar. The deliberately selected free workflow retains Edge and records its explicit audio exception.
- `videoai_graphics.renderer.render_video`: requires a production review before the real-input render. With `audio_mode: natural_game`, preserves source audio tracks and does not call Epidemic. Narrated productions retain supporting Epidemic scoring.
- `aw360.video_renderer`: validates the script before rendering.
- Pure graphics compilation and synthetic graphics demos remain available for layout development; they are not a completed-production approval. Custom FFmpeg scripts and older one-off builders must run `policy_tool.py check` before final delivery and carry out the visual/audio review.

This does not control an unrelated AI application or prevent code from deliberately bypassing the supported entry points. Plan validation cannot prove that a hook is compelling, facts are true, or footage contains the declared action. Inspect the actual media and report that separately. No views or retention outcome is guaranteed.

## Migration and verification

Legacy scripts/configs without `production_review` now need it when entering guarded production paths. Failed Cedar generation stops rather than quietly changing voices. Provider/API costs are not incurred by printing or checking the policy. Tests use mocked providers and synthetic local media.

The original voice preset remains unchanged. Existing rendered videos are not modified by this update.

## Politics mode

`production_review.mode = "politics"` is the user's approved way of editing civic, election and policy explainers (defined 2026-09-12 on the second $5,000 Promise video; reference build: `create_5000_promise_v2.py`, output `output/The_5000_Promise_V2_20260912/`). The canonical rules are the POLITICS MODE entries in [videoai_policy/policy.json](videoai_policy/policy.json); every provider prompt carries them, and `python policy_tool.py prompt --mode politics` emits them with the extra schema fields. In short:

1. **Tell the story through the coverage.** Source genuine broadcast footage from named outlets agreed with the user (CNN, MS NOW, NBC, CBS, ABC, PBS were the set for the $5,000 videos), at native resolution, with a manifest of outlet, programme, date, URL and the exact in/out of every range shown.
2. **Let people speak for themselves.** Short original-audio excerpts cut on word boundaries verified by a secondary transcription of the source window; complete sentences or complete question-and-answer pairs; ~0.1 s lead, ~0.3 s tail; speaker, outlet and programme on screen; unidentified speakers attributed to the event, never guessed. Include the other side's strongest answer.
3. **Everything else is muted and labeled** SOURCE FOOTAGE, MUTED with outlet, programme and date. No source range is shown twice within an export and no clip is replayed muted after playing with sound; the seeks are audited before rendering. Third-party clips inside a source are labeled as re-broadcast.
4. **Structure.** Open at second zero on the sharpest attributed line or the subject's own words; a hard number or document within fifteen seconds; chapters open on a claim or question answered by an excerpt; numbers attributed to whoever used them; accusations called accusations, opinions called opinions; close on the documents that would change the story, not a recap.
5. **Captions and delivery.** Excerpt captions burned from the curated quote text in their own zone, new cue at every speaker change; caption timing re-derived from the audio (transcriber word times drift up to half a second) and checked by transcribing the audio under each cue start; Cedar narration with every take's ending verified; Shorts end within a second of the last word. Deliver SCRIPT.md, FACT_CHECK.md, SOURCE_MANIFEST.json, AUDIO_REPORT.json, QA_REPORT.json, UPLOAD_PACKAGE.md and headline thumbnails.

`python policy_tool.py check <plan.json>` enforces the declarable parts when `mode` is `politics`: a `fact_check` reference, a `sources` list with outlet, date and URL, `used_ranges` with numeric in/out points, a speaker on every original-audio range, and no overlapping range within an export. The check cannot judge whether an excerpt is fair or a caption is in sync; inspect the media and transcribe the audio under the cues.

```powershell
python policy_tool.py prompt --mode politics --format long      # brief another model
python policy_tool.py template --mode politics --format long    # review skeleton with mode + fact_check
python policy_tool.py check output/<video>/main_production_plan.json --duration <seconds>
```
