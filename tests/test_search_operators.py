"""Advanced search operators in note search: tag:/is:/has:/due:, composing with
free text, and bare-date queries still working."""

from datetime import datetime, timedelta

import database as db


def _ids(rows):
    return {r['id'] for r in rows}


def test_tag_operator(make_user, make_note):
    user = make_user('Clay')
    a = make_note(user, content='groceries', tags=['SHOP'])
    make_note(user, content='ideas', tags=['IDEA'])
    res = db.list_notes(user['id'], search='tag:shop')
    assert _ids(res) == {a['id']}


def test_is_todo_and_is_note(make_user, make_note):
    user = make_user('Clay')
    t = make_note(user, content='list', note_type='todo',
                  todos=[{'text': 'x', 'checked': False}])
    n = make_note(user, content='plain note')
    assert _ids(db.list_notes(user['id'], search='is:todo')) == {t['id']}
    assert _ids(db.list_notes(user['id'], search='is:note')) == {n['id']}


def test_has_attachment(make_user, make_note):
    user = make_user('Clay')
    a = make_note(user, content='with file')
    make_note(user, content='no file')
    db.add_attachment(a['id'], 'f.pdf', 'f.pdf', 'application/pdf', 5)
    assert _ids(db.list_notes(user['id'], search='has:attachment')) == {a['id']}


def test_due_today_and_overdue(make_user, make_note):
    user = make_user('Clay')
    today = datetime.now().date().isoformat()
    past = (datetime.now() - timedelta(days=2)).isoformat(timespec='seconds')
    # End of today so it's "due today" but not yet overdue, whatever time it runs.
    a = make_note(user, content='due today', note_type='todo',
                  todos=[{'text': 'a', 'checked': False, 'due_at': today + 'T23:59'}])
    b = make_note(user, content='overdue', note_type='todo',
                  todos=[{'text': 'b', 'checked': False, 'due_at': past}])
    assert _ids(db.list_notes(user['id'], search='due:today')) == {a['id']}
    assert _ids(db.list_notes(user['id'], search='due:overdue')) == {b['id']}


def test_operator_composes_with_free_text(make_user, make_note):
    user = make_user('Clay')
    a = make_note(user, content='buy milk', note_type='todo',
                  todos=[{'text': 'm', 'checked': False}])
    make_note(user, content='buy milk', note_type='note')   # not a todo
    make_note(user, content='sell milk', note_type='todo',
              todos=[{'text': 's', 'checked': False}])
    res = db.list_notes(user['id'], search='is:todo buy')
    assert _ids(res) == {a['id']}


def test_bare_date_query_still_works(make_user, make_note):
    user = make_user('Clay')
    n = make_note(user, content='dated note')
    today = datetime.now().date().isoformat()
    assert n['id'] in _ids(db.list_notes(user['id'], search=today))
