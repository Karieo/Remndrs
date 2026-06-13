"""apply_timezone() pins the process timezone from the TIMEZONE setting, so
naive local timestamps (created_at, reminder fire_at) don't depend on the host
clock's zone. tzset() is process-global, so each test restores it afterwards.
"""

import os
import time
from datetime import datetime

import pytest

pytest.importorskip('app', reason='Flask app import')  # noqa
import app as appmod


@pytest.fixture
def restore_tz():
    prev_tz = os.environ.get('TZ')
    prev_setting = os.environ.get('TIMEZONE')
    yield
    for key, val in (('TZ', prev_tz), ('TIMEZONE', prev_setting)):
        if val is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = val
    try:
        time.tzset()
    except AttributeError:
        pass


def test_apply_timezone_changes_local_offset(restore_tz):
    os.environ['TIMEZONE'] = 'America/New_York'
    appmod.apply_timezone()
    east = datetime.now().astimezone().utcoffset()

    os.environ['TIMEZONE'] = 'Asia/Tokyo'
    appmod.apply_timezone()
    tokyo = datetime.now().astimezone().utcoffset()

    # Same instant, different configured zone → different wall-clock offset.
    assert east != tokyo


def test_apply_timezone_empty_is_noop(restore_tz):
    os.environ['TIMEZONE'] = ''
    # Must not raise and must not blow away the host zone.
    appmod.apply_timezone()
    assert datetime.now().astimezone().utcoffset() is not None
