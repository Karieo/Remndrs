"""Tier 2 — voice transcript cleanup and spoken tag extraction (voice.py).

All pure regex logic; no OpenAI calls involved.
"""

import voice


# ── clean_transcript ───────────────────────────────────────────────────────

def test_clean_transcript_removes_fillers():
    out = voice.clean_transcript('um I need to uh buy milk')
    assert 'um' not in out.lower().split()
    assert 'buy milk' in out.lower()


def test_clean_transcript_capitalises_first_letter():
    assert voice.clean_transcript('hello there')[0] == 'H'


def test_clean_transcript_capitalises_after_sentence_end():
    out = voice.clean_transcript('first thing. second thing')
    assert 'Second thing' in out


def test_clean_transcript_handles_empty():
    assert voice.clean_transcript('') == ''
    assert voice.clean_transcript(None) == ''


def test_clean_transcript_preserves_hashtags():
    out = voice.clean_transcript('buy milk #groceries')
    assert '#groceries' in out


# ── extract_voice_tags ─────────────────────────────────────────────────────

def test_extract_voice_tags_always_includes_voice():
    assert voice.extract_voice_tags('nothing here') == ['VOICE']


def test_extract_voice_tags_literal_hashtag():
    assert 'IDEAS' in voice.extract_voice_tags('a thought #ideas')


def test_extract_voice_tags_spoken_hashtag_word():
    assert 'WORK' in voice.extract_voice_tags('note this hashtag work please')


def test_extract_voice_tags_tag_this_as():
    assert 'TRAVEL' in voice.extract_voice_tags('remember to pack, tag this as travel')


def test_extract_voice_tags_deduplicates():
    tags = voice.extract_voice_tags('#work and hashtag work')
    assert tags.count('WORK') == 1
