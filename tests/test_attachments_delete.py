"""Deleting an attachment: removes the row and strips its markdown link from
the note body; ownership is enforced."""

import database as db


def _login(client, name='Clay'):
    client.post('/api/auth/login', json={'login': name, 'password': 'pw'})


def test_delete_attachment_strips_link_and_row(client, make_user):
    user = make_user('Clay'); _login(client)
    saved = '2026-06-14-abc123-photo.png'
    note = db.create_note(
        user['id'],
        content='Here is a pic\n\n![photo](/api/attachments/%s)' % saved)
    att_id = db.add_attachment(note['id'], 'photo.png', saved, 'image/png', 10)

    resp = client.delete('/api/attachments/' + att_id)
    assert resp.status_code == 200
    assert db.get_attachment(att_id) is None
    refreshed = db.get_note(note['id'])
    assert '/api/attachments/' not in refreshed['content']
    assert 'Here is a pic' in refreshed['content']


def test_delete_attachment_404_for_unknown(client, make_user):
    make_user('Clay'); _login(client)
    assert client.delete('/api/attachments/nope').status_code == 404


def test_cannot_delete_attachment_on_others_private_note(client, make_user):
    owner = make_user('Owner')
    other = make_user('Other')
    note = db.create_note(other['id'], content='x', feed='private')
    att_id = db.add_attachment(note['id'], 'f.pdf', 'f.pdf', 'application/pdf', 5)
    _login(client, 'Owner')
    assert client.delete('/api/attachments/' + att_id).status_code == 404
    assert db.get_attachment(att_id) is not None
