"""Note templates: db CRUD + the /api/templates routes (create/list/delete,
per-user scoping and ownership)."""

from html.parser import HTMLParser

import database as db


# ── Feed page DOM structure ──────────────────────────────────────────────────

class _AncestryParser(HTMLParser):
    """Record, for every element carrying an id, the list of ancestor ids.

    Models the browser's open-element stack with the same leniency: a dropped
    close tag leaves its element open, so later siblings nest inside it.
    """

    def __init__(self):
        super().__init__()
        self._stack = []        # (tag, id_or_None) for each open element
        self.ancestors = {}     # id -> [ancestor ids, outermost first]

    def handle_starttag(self, tag, attrs):
        eid = dict(attrs).get('id')
        if eid is not None:
            self.ancestors[eid] = [i for _t, i in self._stack if i]
        self._stack.append((tag, eid))

    def handle_startendtag(self, tag, attrs):
        # Self-closing (e.g. SVG <path/>) — never opens a scope.
        pass

    def handle_endtag(self, tag):
        for i in range(len(self._stack) - 1, -1, -1):
            if self._stack[i][0] == tag:
                del self._stack[i:]
                return


def _feed_html(client, make_user):
    make_user('Clay')
    client.post('/api/auth/login', json={'login': 'Clay', 'password': 'pw'})
    return client.get('/').get_data(as_text=True)


def test_feed_modals_are_not_nested(client, make_user):
    """Regression: a dropped </div> in the reminders sheet once left
    #remindersOverlay unclosed, nesting every later modal inside it. Because
    that overlay is display:none, the composer / settings / share sheets then
    rendered at 0x0 — invisible with no JS error. Each modal overlay must be a
    top-level element, never a descendant of another overlay."""
    parser = _AncestryParser()
    parser.feed(_feed_html(client, make_user))
    for modal in ('composer', 'settingsOverlay', 'shareOverlay', 'tagAddOverlay',
                  'tagEditOverlay', 'attachmentsOverlay', 'templatesOverlay'):
        assert modal in parser.ancestors, f'{modal} missing from feed page'
        assert 'remindersOverlay' not in parser.ancestors[modal], (
            f'#{modal} is nested inside #remindersOverlay — a close tag was '
            f'dropped, so this modal renders 0x0 inside a hidden parent')


def _login(client, name='Clay'):
    client.post('/api/auth/login', json={'login': name, 'password': 'pw'})


# ── db ───────────────────────────────────────────────────────────────────────

def test_template_crud(make_user):
    user = make_user('Clay')
    t = db.create_template(user['id'], 'Standup', '## Standup\n- yesterday\n- today')
    assert t['title'] == 'Standup'
    assert [x['id'] for x in db.list_templates(user['id'])] == [t['id']]
    db.delete_template(t['id'])
    assert db.list_templates(user['id']) == []


def test_templates_are_per_user(make_user):
    clay = make_user('Clay')
    mia = make_user('Mia')
    db.create_template(clay['id'], 'Clay tpl', 'x')
    assert db.list_templates(mia['id']) == []


# ── routes ─────────────────────────────────────────────────────────────────

def test_create_list_delete_routes(client, make_user):
    user = make_user('Clay'); _login(client)
    resp = client.post('/api/templates', json={'title': 'Journal', 'body': '# {date}'})
    assert resp.status_code == 201
    tid = resp.get_json()['id']
    assert [t['title'] for t in client.get('/api/templates').get_json()] == ['Journal']
    assert client.delete(f'/api/templates/{tid}').status_code == 200
    assert client.get('/api/templates').get_json() == []


def test_create_requires_title_and_body(client, make_user):
    make_user('Clay'); _login(client)
    assert client.post('/api/templates', json={'title': 'x'}).status_code == 400
    assert client.post('/api/templates', json={'body': 'x'}).status_code == 400


def test_cannot_delete_others_template(client, make_user):
    owner = make_user('Owner')
    other = make_user('Other')
    t = db.create_template(other['id'], 'Theirs', 'body')
    _login(client, 'Owner')
    assert client.delete(f"/api/templates/{t['id']}").status_code == 404
    assert db.get_template(t['id']) is not None   # untouched
