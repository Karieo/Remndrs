"""Guard against a broken static/js/app.js reaching production.

A bad merge once duplicated a function and left an unbalanced brace, so the
whole script failed to parse and the web UI went blank — with no test to catch
it (JS has no other coverage here). This parses app.js with Node's script
parser; a syntax error fails the suite. Skipped when Node isn't installed.
"""

import os
import shutil
import subprocess

import pytest

_APP_JS = os.path.join(os.path.dirname(__file__), '..', 'static', 'js', 'app.js')


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
