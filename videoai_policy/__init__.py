"""Shared, provider-independent editorial defaults and deterministic plan checks.

No network calls, environment variables, model SDKs, or paid services at import.
Validation examines declared plans/text; it cannot judge unseen footage or truth.
"""
from __future__ import annotations
import copy
import json
import math
from pathlib import Path
import re

class ProductionPolicyError(ValueError):
    pass

def load_policy():
    data = json.loads(Path(__file__).with_name('policy.json').read_text(encoding='utf-8'))
    if not isinstance(data.get('rules'), list) or not data['rules']:
        raise ProductionPolicyError('Shared production policy is missing or invalid.')
    return data

def review_template(content_type='documentary', video_format='short'):
    return {'content_type': content_type, 'format': video_format, 'hook_start_seconds': 0,
            'hook': '', 'first_payoff_seconds': None, 'first_payoff': '', 'pacing_review': '',
            'audio_mode': 'natural_game' if content_type == 'gameplay' else 'cedar',
            'standalone': True, 'overrides': {}}

def policy_prompt(*, content_type='documentary', video_format='short', include_review=True):
    p = load_policy()
    text = f"VIDEOAI SHARED PRODUCTION POLICY {p['version']}\n"
    text += '\n'.join(f'{i+1}. {rule}' for i, rule in enumerate(p['rules']))
    text += '\nThese user-approved production defaults replace conflicting legacy style instructions. Explicit user requests still take precedence.\n'
    if include_review:
        text += ('Add a top-level production_review object to the requested JSON schema. Fill every blank '
                 'with a concrete description of this edit, and set first_payoff_seconds to its actual planned '
                 'time. Do not copy placeholders. For any exception, overrides[rule_id] must contain '
                 'reason and user_request strings quoting the actual user choice; never invent authorization. '
                 'Allowed exceptions: hook, payoff, pacing, audio, standalone. Template:\n')
        text += json.dumps(review_template(content_type, video_format), ensure_ascii=False)
    return text

def _number(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ProductionPolicyError(f'{name} must be a finite number.')
    return float(value)

def _text(value):
    return isinstance(value, str) and len(value.strip()) >= 6 and value.strip().lower() not in {'placeholder', 'fill in', 'todo todo', 'example'}

def validate_plan(data, *, duration=None):
    if not isinstance(data, dict):
        raise ProductionPolicyError('Production input must be a JSON object.')
    p = load_policy(); review = data.get('production_review')
    if not isinstance(review, dict):
        raise ProductionPolicyError('Missing production_review. Run python policy_tool.py template, fill it from the actual edit, and include it in the config/script.')
    overrides = review.get('overrides', {})
    if not isinstance(overrides, dict):
        raise ProductionPolicyError('overrides must be an object.')
    for key, value in overrides.items():
        if key not in {'hook','payoff','pacing','audio','standalone'} or not isinstance(value, dict) or not all(_text(value.get(f)) for f in ['reason','user_request']):
            raise ProductionPolicyError(f'Invalid override {key!r}; record the real user request and the reason.')
    def require(condition, message, exception=None):
        if not condition and exception not in overrides:
            raise ProductionPolicyError(message)
    require(review.get('content_type') in {'gameplay','documentary','lore','other'}, 'Unknown content_type.')
    require(review.get('format') in {'long','short'}, 'format must be long or short.')
    for key in ['hook','first_payoff','pacing_review']:
        require(_text(review.get(key)), f'production_review.{key} needs a concrete edit description.')
    hook = _number(review.get('hook_start_seconds'), 'hook_start_seconds')
    payoff = _number(review.get('first_payoff_seconds'), 'first_payoff_seconds')
    require(hook >= 0 and payoff >= hook, 'Hook/payoff times must be nonnegative and ordered.')
    require(hook == p['hook_start_seconds'], 'Start the hook at second zero.', 'hook')
    require(payoff <= p['first_payoff_deadline_seconds'], 'First meaningful payoff must arrive within 15 seconds.', 'payoff')
    if duration is not None:
        duration = _number(duration, 'duration')
        require(duration > 0 and payoff < duration, 'First payoff must occur before the video ends.')
    mode = review.get('audio_mode')
    require(mode in {'natural_game','cedar','explicit_override'}, 'Unknown audio_mode.')
    expected = 'natural_game' if review['content_type'] == 'gameplay' else 'cedar'
    require(mode == expected, f'{review["content_type"]} defaults to {expected}; document an explicit user choice to change audio.', 'audio')
    require(mode != 'explicit_override' or 'audio' in overrides, 'explicit_override requires the actual user audio request.')
    if review['format'] == 'short':
        require(review.get('standalone') is True, 'Shorts must stand alone unless explicitly requested as trailers.', 'standalone')
    for segment in data.get('shots', data.get('scenes', [])):
        if isinstance(segment, dict) and segment.get('role') in {'loading','redundant_travel','empty_pause'}:
            require(_text(segment.get('editorial_reason')), 'Remove downtime or document why this particular moment serves the story.', 'pacing')
    return {'policy_version': p['version'], 'status': 'plan_checked',
            'limitations': 'Checks declared timings, text and editorial descriptions; does not establish actual footage quality or audience performance.',
            'overrides': copy.deepcopy(overrides)}

def validate_script(data, *, duration=None):
    result = validate_plan(data, duration=duration)
    text = data.get('narration_script', data.get('full_voiceover_text', ''))
    if not isinstance(text, str):
        raise ProductionPolicyError('Narration must be text.')
    overrides = data['production_review'].get('overrides', {})
    if data['production_review']['audio_mode'] != 'natural_game' and not text.strip():
        raise ProductionPolicyError('Narrated scripts must contain narration.')
    if re.match(r'^\s*(welcome\b|hello everyone\b|hey guys\b|in today.?s video\b|before we (?:begin|start)\b)', text, re.I) and 'hook' not in overrides:
        raise ProductionPolicyError('Opening contains a greeting or preamble; lead with the promised content.')
    if any(float(v) > 1.05 for v in re.findall(r'\[pause\s+(\d+(?:\.\d+)?)\s*s?\]', text, re.I)) and 'pacing' not in overrides:
        raise ProductionPolicyError('Remove forced long pause tags; preserve natural phrasing.')
    if data['production_review']['format'] == 'short' and re.search(r'(?:watch|check out|link to)\s+(?:the\s+)?(?:full|long(?:[ -]form)?)\s+video', text, re.I) and 'standalone' not in overrides:
        raise ProductionPolicyError('Standalone Short contains a main-video promotion.')
    return result

def checked_script(data, *, duration=None):
    result = copy.deepcopy(data)
    result['production_policy_check'] = validate_script(result, duration=duration)
    return result
