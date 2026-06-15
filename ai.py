"""AI helpers backed by OpenAI. Self-disabling like every other integration:
with no OPENAI_API_KEY set, calls no-op (return empty). The openai SDK is
imported lazily so the app runs without it installed, and the key is read at
call time (it's editable at runtime from Settings)."""

import json
import logging
import os
import re

log = logging.getLogger(__name__)


def configured():
    return bool(os.getenv('OPENAI_API_KEY'))


def _parse_tags(text):
    """Pull a list of tag strings out of the model's reply — a JSON array if it
    returned one, else a comma/newline split as a fallback."""
    text = (text or '').strip()
    match = re.search(r'\[.*\]', text, re.S)
    if match:
        try:
            return json.loads(match.group(0))
        except (ValueError, TypeError):
            pass
    return re.split(r'[,\n]+', text)


def _normalize(name):
    """A tag name: strip #, drop spaces/punctuation, uppercase (matches the
    app's global-uppercase tag convention)."""
    return re.sub(r'[^A-Za-z0-9_-]', '', str(name)).upper()


def suggest_tags(content, existing=None, limit=6):
    """Suggest up to `limit` topic tags for a note's content. Returns [] when
    OpenAI isn't configured or on any error — never raises, never blocks save."""
    content = (content or '').strip()
    if not content or not configured():
        return []
    existing = [_normalize(t) for t in (existing or []) if str(t).strip()]
    try:
        import openai
        client = openai.OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
        prompt = (
            f'Suggest up to {limit} short topic tags for the note below. '
            'Each tag is a single word or hyphenated-phrase, no spaces, no "#". '
            f'Prefer reusing these existing tags when relevant: '
            f'{", ".join(existing) or "(none)"}. '
            'Return ONLY a JSON array of strings.\n\nNote:\n' + content[:2000])
        resp = client.chat.completions.create(
            model=os.getenv('OPENAI_TAG_MODEL', 'gpt-4o-mini'),
            messages=[{'role': 'user', 'content': prompt}],
            temperature=0.2, max_tokens=120)
        raw = _parse_tags(resp.choices[0].message.content)
    except Exception:
        log.exception('AI tag suggestion failed')
        return []
    out = []
    for tag in raw:
        name = _normalize(tag)
        if name and name not in existing and name not in out:
            out.append(name)
    return out[:limit]


def summarize(content):
    """A 1-2 sentence TL;DR of a note's content. Returns '' when OpenAI isn't
    configured or on any error — never raises."""
    content = (content or '').strip()
    if not content or not configured():
        return ''
    try:
        import openai
        client = openai.OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
        prompt = ('Summarize the note below in 1-2 short sentences (a TL;DR). '
                  'Plain text, no preamble, no markdown.\n\nNote:\n' + content[:4000])
        resp = client.chat.completions.create(
            model=os.getenv('OPENAI_TAG_MODEL', 'gpt-4o-mini'),
            messages=[{'role': 'user', 'content': prompt}],
            temperature=0.3, max_tokens=160)
        return (resp.choices[0].message.content or '').strip()
    except Exception:
        log.exception('AI summarize failed')
        return ''
