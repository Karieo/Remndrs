"""Whisper transcription, transcript cleanup, spoken tag extraction."""

import logging
import os
import re

import ai

log = logging.getLogger(__name__)

WHISPER_MAX_BYTES = 25 * 1024 * 1024


def openai_configured():
    return bool(os.getenv('OPENAI_API_KEY'))


def transcribe(audio_path: str) -> str:
    """Send audio file to OpenAI Whisper. Returns raw transcript."""
    if os.path.getsize(audio_path) > WHISPER_MAX_BYTES:
        raise ValueError('Audio file exceeds the 25MB Whisper limit')
    import openai
    client = openai.OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
    with open(audio_path, 'rb') as f:
        result = client.audio.transcriptions.create(
            model='whisper-1',
            file=f,
            response_format='text')
    return result if isinstance(result, str) else str(result)


def clean_transcript(raw: str) -> str:
    """Remove filler words, fix punctuation, normalise capitalisation.

    Does not alter proper nouns, tag names, or content meaning.
    #HASHTAG patterns are preserved exactly.
    """
    fillers = r'\b(um+|uh+|like,?\s|you know,?\s|sort of,?\s|kind of,?\s|'
    fillers += r'basically,?\s|literally,?\s|honestly,?\s|actually,?\s|'
    fillers += r'i mean,?\s|right\??\s*$)\b'

    text = re.sub(fillers, '', raw or '', flags=re.IGNORECASE)
    text = re.sub(r'\s+', ' ', text).strip()
    text = re.sub(r'(?<=[.!?])\s+([a-z])', lambda m: m.group(0).upper(), text)
    if text:
        text = text[0].upper() + text[1:]
    return text


def smart_clean(raw: str) -> str:
    """Clean a transcript, preferring the AI pass (punctuation, paragraphs,
    filler removal) and falling back to the deterministic regex pass when
    OpenAI is unavailable or errors. Result is non-empty whenever `raw` is."""
    return ai.cleanup_transcript(raw) or clean_transcript(raw)


def extract_voice_tags(transcript: str) -> list:
    """Extract spoken hashtags: '#ideas', 'hashtag ideas', 'tag this as ideas'."""
    tags = ['VOICE']
    tags += [t.upper() for t in re.findall(r'#([A-Za-z0-9_]+)', transcript or '')]
    tags += [t.upper() for t in re.findall(r'hashtag\s+([A-Za-z0-9_]+)',
                                           transcript or '', re.IGNORECASE)]
    tags += [t.upper() for t in re.findall(r'tag\s+this\s+as\s+([A-Za-z0-9_]+)',
                                           transcript or '', re.IGNORECASE)]
    return list(dict.fromkeys(tags))
