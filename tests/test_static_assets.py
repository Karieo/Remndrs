"""Guard against a broken static/js/app.js reaching production.

A bad merge once duplicated a function and left an unbalanced brace, so the
whole script failed to parse and the web UI went blank — with no test to catch
it (JS has no other coverage here). This parses app.js with Node's script
parser; a syntax error fails the suite. Skipped when Node isn't installed.
"""

import os
import re
import shutil
import subprocess

import pytest

_STATIC = os.path.join(os.path.dirname(__file__), '..', 'static')
_APP_JS = os.path.join(_STATIC, 'js', 'app.js')
_APP_CSS = os.path.join(_STATIC, 'css', 'app.css')


def _rule_body(css, selector):
    """Return the declaration block for an exact top-level selector, or None."""
    m = re.search(r'(?m)^' + re.escape(selector) + r'\s*\{([^}]*)\}', css)
    return m.group(1) if m else None


def _transition(body):
    m = re.search(r'transition\s*:([^;]*)', body or '')
    return m.group(1) if m else ''


def test_app_js_parses():
    node = shutil.which('node')
    if not node:
        pytest.skip('node not available to parse app.js')
    result = subprocess.run(
        [node, '-e',
         "const fs=require('fs');"
         "new (require('vm').Script)(fs.readFileSync(process.argv[1],'utf8'),"
         "{filename:'app.js'});",
         _APP_JS],
        capture_output=True, text=True)
    assert result.returncode == 0, (
        'static/js/app.js failed to parse (syntax error — likely a bad '
        f'merge):\n{result.stderr}')


def test_card_menu_open_transform_is_instant():
    """The card ··· menu is positioned with position:fixed in JS, which only
    anchors to the viewport if no ancestor has a transform. .card.menu-open sets
    transform:none for exactly this reason — but .card animates `transform`, so
    if .menu-open doesn't also drop transform from its transition, transform:none
    fades in over .1s. During that fade the card still has a transform and
    becomes the menu's containing block, so the menu pops up in the wrong place
    (off by the card's offset) until the lift settles.

    Invariant: when the menu opens, the card's transform must NOT be animated.
    """
    with open(_APP_CSS, encoding='utf-8') as f:
        css = f.read()

    menu_open = _rule_body(css, '.card.menu-open')
    assert menu_open is not None, '.card.menu-open rule not found'
    assert 'transform:none' in menu_open.replace(' ', ''), (
        '.card.menu-open must set transform:none so the fixed menu anchors to '
        'the viewport, not the card')

    # The transition that actually applies to .card.menu-open: its own override
    # if present, else inherited from .card. It must not animate `transform`.
    effective = _transition(menu_open) or _transition(_rule_body(css, '.card'))
    assert 'transform' not in effective, (
        'transform must not be animated when the menu opens, or transform:none '
        'fades in and the fixed ··· menu mispositions during the animation. '
        f'Effective transition for .card.menu-open: "{effective.strip()}"')
