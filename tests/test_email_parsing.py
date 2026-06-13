"""Tier 2 — inbound email parsing (email_inbound.py).

HTML stripping, tag extraction (subject prefixes, declared tag lines,
hashtag-only lines) and reminder detection are all pure regex/parse logic.
"""

import email_inbound as ei


# ── strip_html ─────────────────────────────────────────────────────────────

def test_strip_html_extracts_text():
    # Text nodes are space-joined; assert content survives rather than exact spacing.
    out = ei.strip_html('<p>Hello <b>world</b></p>')
    assert 'Hello' in out and 'world' in out
    assert '<' not in out


def test_strip_html_handles_empty_and_none():
    assert ei.strip_html('') == ''
    assert ei.strip_html(None) == ''


# ── _extract_tag_lines ─────────────────────────────────────────────────────

def test_extract_tag_lines_dedicated_tags_line():
    body, tags = ei._extract_tag_lines('Buy stuff\nTags: groceries, costco')
    assert body == 'Buy stuff'
    assert tags == ['GROCERIES', 'COSTCO']


def test_extract_tag_lines_hashtag_only_line():
    body, tags = ei._extract_tag_lines('Some idea\n#work #urgent')
    assert body == 'Some idea'
    assert tags == ['WORK', 'URGENT']


def test_extract_tag_lines_spaces_become_underscores():
    _body, tags = ei._extract_tag_lines('Tags: to do, follow up')
    assert tags == ['TO_DO', 'FOLLOW_UP']


def test_extract_tag_lines_no_tags():
    body, tags = ei._extract_tag_lines('just a normal note\nwith two lines')
    assert tags == []
    assert 'normal note' in body


# ── _extract_tags (subject prefixes + hashtags) ────────────────────────────

def test_extract_tags_always_includes_email():
    assert ei._extract_tags('hi', 'there') == ['EMAIL']


def test_extract_tags_subject_bracket_prefix():
    tags = ei._extract_tags('[Ideas] new plan', 'body')
    assert 'IDEAS' in tags


def test_extract_tags_paren_prefix_and_hashtags():
    tags = ei._extract_tags('(Personal) note', 'body with #travel')
    assert 'PERSONAL' in tags
    assert 'TRAVEL' in tags


def test_extract_tags_excludes_shared_prefix():
    tags = ei._extract_tags('[shared] dinner', 'body')
    assert 'SHARED' not in tags


def test_extract_tags_deduplicates():
    tags = ei._extract_tags('note #work', 'more #work text')
    assert tags.count('WORK') == 1


# ── _reminder_request ──────────────────────────────────────────────────────

def test_reminder_request_detects_leading_keyword():
    result = ei._reminder_request('Remind me tomorrow at 9am to call the bank', '')
    assert result is not None
    fire_at, message = result
    assert 'call the bank' in message


def test_reminder_request_ignores_passing_mention():
    # "remind" not leading and not "remind me" → not a reminder.
    assert ei._reminder_request('Notes', 'This will remind you of summer') is None


def test_reminder_request_skips_quoted_first_line():
    # Forwarded/quoted lines (starting with > or ---) are not candidates.
    assert ei._reminder_request('Fwd: hi', '> remind me tomorrow to x') is None
