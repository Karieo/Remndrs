/* Remndrs frontend — minimal functional UI. Final design lands separately. */

const state = {
  feed: 'private',
  tag: null,
  search: '',
  tags: [],
  editingNoteId: null,
  composerMode: 'note',
  previews: {},
};

const $ = (sel) => document.querySelector(sel);
const cardsEl = $('#cards');

// ── Data loading ─────────────────────────────────────────

async function api(path, opts = {}) {
  const res = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...opts,
  });
  if (res.status === 401) { window.location = '/login'; return null; }
  return res.json();
}

async function loadTags() {
  state.tags = await api('/api/tags') || [];
  renderTagBar();
}

async function loadNotes() {
  const params = new URLSearchParams();
  params.set('feed', state.feed);
  if (state.tag) params.set('tag', state.tag);
  if (state.search) params.set('search', state.search);
  const notes = await api('/api/notes?' + params) || [];
  let events = [];
  if (!state.search) {
    events = await api('/api/calendar/events') || [];
    events = events.filter((e) => state.feed === 'shared' ? e.feed === 'shared' : e.feed === 'private');
    if (state.tag && state.tag !== 'CALENDAR') events = [];
  }
  renderFeed(notes, events);
}

// ── Tag bar ──────────────────────────────────────────────

function renderTagBar() {
  const wrap = $('#tag-pills');
  wrap.innerHTML = '';
  for (const tag of state.tags) {
    if (!tag.count && tag.name !== state.tag) continue;
    const btn = document.createElement('button');
    btn.className = 'tag-pill';
    btn.style.background = tag.color;
    btn.textContent = '#' + tag.name;
    if (state.tag === tag.name) btn.classList.add('active');
    else if (state.tag) btn.classList.add('dimmed');
    btn.onclick = () => setTagFilter(state.tag === tag.name ? null : tag.name);
    wrap.appendChild(btn);
  }
  $('#clear-filter-btn').hidden = !state.tag;
  const label = $('#filter-label');
  label.hidden = !state.tag;
  if (state.tag) label.textContent = 'Showing #' + state.tag;
}

function setTagFilter(tag) {
  state.tag = tag;
  if (tag) { state.search = ''; $('#search').value = ''; }
  renderTagBar();
  loadNotes();
}

// ── Cards ────────────────────────────────────────────────

function renderFeed(notes, events) {
  cardsEl.innerHTML = '';
  const items = [
    ...notes.map((n) => ({ kind: 'note', at: n.created_at, data: n })),
    ...events.map((e) => ({ kind: 'event', at: e.start_at, data: e })),
  ];
  // Pinned notes first, then reverse-chronological
  items.sort((a, b) => {
    const ap = a.kind === 'note' && a.data.pinned ? 1 : 0;
    const bp = b.kind === 'note' && b.data.pinned ? 1 : 0;
    if (ap !== bp) return bp - ap;
    return (b.at || '').localeCompare(a.at || '');
  });
  for (const item of items) {
    cardsEl.appendChild(item.kind === 'note' ? noteCard(item.data) : eventCard(item.data));
  }
}

function fmtDate(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' }) +
    ' · ' + d.toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' });
}

function highlight(html) {
  if (!state.search) return html;
  try {
    const re = new RegExp('(' + state.search.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + ')', 'gi');
    return html.replace(re, '<mark>$1</mark>');
  } catch { return html; }
}

function noteCard(note) {
  const card = document.createElement('div');
  card.className = 'card';
  card.dataset.id = note.id;
  if (note.tags.length) {
    card.classList.add('has-accent');
    card.style.borderLeftColor = note.tags[0].color;
  }
  if (note.pinned) card.classList.add('pinned');

  let head = '';
  if (note.pinned) head += '<span class="pinned-badge">⚑ PINNED</span> ';
  head += `<div class="card-meta">${fmtDate(note.created_at)}` +
    (note.feed === 'shared' ? ' 👤' : '') + '</div>';

  let body = '';
  if (note.type === 'todo' && note.todos.length) {
    const done = note.todos.filter((t) => t.checked).length;
    const color = note.tags.length ? note.tags[0].color : '#4ade80';
    head += `<span class="todo-counter">${done}/${note.todos.length} ` +
      `<span class="todo-progress"><span style="width:${(done / note.todos.length) * 100}%;background:${color}"></span></span></span>`;
    body += `<div class="content">${highlight(marked.parse(note.content || ''))}</div>`;
    for (const t of note.todos) {
      body += `<div class="todo-item${t.checked ? ' checked' : ''}">` +
        `<input type="checkbox" data-todo="${t.id}" ${t.checked ? 'checked' : ''}><label>${escapeHtml(t.text)}</label></div>`;
    }
  } else {
    body = `<div class="content">${highlight(marked.parse(note.content || ''))}</div>`;
  }

  let tags = '<div class="card-tags">';
  for (const t of note.tags) {
    tags += `<span class="tag-pill" style="background:${t.color}">#${t.name}</span>`;
  }
  tags += '</div>';

  const source = note.source !== 'web'
    ? `<span class="source-badge">${note.source.toUpperCase()}</span>` : '';

  card.innerHTML = head + body + tags + source +
    '<button class="menu-btn" title="Delete">✕</button>';

  card.querySelector('.menu-btn').onclick = async (e) => {
    e.stopPropagation();
    if (!confirm('Delete this note?')) return;
    await api('/api/notes/' + note.id, { method: 'DELETE' });
  };
  card.querySelectorAll('input[data-todo]').forEach((cb) => {
    cb.onclick = async (e) => {
      e.stopPropagation();
      const todos = note.todos.map((t) =>
        t.id === cb.dataset.todo ? { ...t, checked: cb.checked } : t);
      await api('/api/notes/' + note.id, {
        method: 'PATCH', body: JSON.stringify({ todos }),
      });
    };
  });
  card.onclick = () => openComposer(note);

  renderLinkPreviews(card, note.content || '');
  return card;
}

function eventCard(ev) {
  const card = document.createElement('div');
  card.className = 'card calendar';
  if (new Date(ev.end_at) < new Date()) card.classList.add('past');
  if (ev.deleted) card.classList.add('orphaned');
  const time = ev.all_day ? new Date(ev.start_at).toLocaleDateString() : fmtDate(ev.start_at);
  card.innerHTML =
    `<span class="cal-badge">${escapeHtml(ev.calendar_name)}</span>` +
    (ev.deleted ? ' <span class="pinned-badge">⚠️ ORPHANED</span>' : '') +
    `<div class="card-meta">${time}</div>` +
    `<strong>${escapeHtml(ev.title)}</strong>` +
    (ev.location ? `<div class="muted">📍 ${escapeHtml(ev.location)}</div>` : '') +
    `<div class="event-notes"></div>` +
    `<button class="add-note-btn">+ Add note</button>`;
  card.querySelector('.add-note-btn').onclick = async () => {
    const ta = document.createElement('textarea');
    ta.placeholder = 'Note (saves on blur)';
    card.appendChild(ta);
    ta.focus();
    ta.onblur = async () => {
      if (ta.value.trim()) {
        await api('/api/calendar/notes', {
          method: 'POST',
          body: JSON.stringify({ event_id: ev.id, content: ta.value }),
        });
      }
      ta.remove();
    };
  };
  api('/api/calendar/events/' + ev.id).then((full) => {
    if (!full || !full.notes) return;
    const wrap = card.querySelector('.event-notes');
    wrap.innerHTML = full.notes.map((n) =>
      `<div class="content">${marked.parse(n.content || '')}</div>`).join('');
  });
  return card;
}

function escapeHtml(s) {
  const div = document.createElement('div');
  div.textContent = s || '';
  return div.innerHTML;
}

function renderLinkPreviews(card, content) {
  const urls = (content.match(/https?:\/\/[^\s)>\]]+/g) || []).slice(0, 2);
  for (const url of urls) {
    const render = (p) => {
      if (!p || p.error || !p.title) return;
      const a = document.createElement('a');
      a.className = 'link-preview';
      a.href = url; a.target = '_blank';
      a.innerHTML = `<div class="lp-title">${escapeHtml(p.title)}</div>` +
        (p.description ? `<div class="lp-desc">${escapeHtml(p.description)}</div>` : '');
      card.querySelector('.content')?.appendChild(a);
    };
    if (state.previews[url]) render(state.previews[url]);
    else fetch('/api/preview?url=' + encodeURIComponent(url))
      .then((r) => r.json()).then((p) => { state.previews[url] = p; render(p); });
  }
}

// ── Composer ─────────────────────────────────────────────

function openComposer(note) {
  state.editingNoteId = note ? note.id : null;
  state.composerMode = note && note.type === 'todo' ? 'todo' : 'note';
  $('#composer-content').value = note ? note.content : '';
  $('#composer-tags').value = note ? note.tags.map((t) => t.name).join(', ') : '';
  document.querySelector(`input[name="cfeed"][value="${note ? note.feed : state.feed}"]`).checked = true;
  $('#todo-items').innerHTML = '';
  if (note && note.type === 'todo') {
    $('#todo-title').value = note.content;
    for (const t of note.todos) addTodoRow(t.text, t.checked);
  } else {
    $('#todo-title').value = '';
  }
  setComposerTab(state.composerMode);
  $('#composer-overlay').hidden = false;
  ($('#composer-content')).focus();
}

function setComposerTab(mode) {
  state.composerMode = mode;
  $('#tab-note').classList.toggle('active', mode === 'note');
  $('#tab-todo').classList.toggle('active', mode === 'todo');
  $('#composer-content').hidden = mode !== 'note';
  $('#todo-editor').hidden = mode !== 'todo';
  if (mode === 'todo' && !$('#todo-items').children.length) addTodoRow();
}

function addTodoRow(text = '', checked = false) {
  const li = document.createElement('li');
  li.innerHTML = `<span class="todo-item"><input type="checkbox" ${checked ? 'checked' : ''}>` +
    `<input type="text" value="${escapeHtml(text)}" placeholder="To-do item"></span>`;
  const input = li.querySelector('input[type="text"]');
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') { e.preventDefault(); addTodoRow(); }
    if (e.key === 'Backspace' && !input.value && $('#todo-items').children.length > 1) {
      e.preventDefault();
      const prev = li.previousElementSibling;
      li.remove();
      prev?.querySelector('input[type="text"]')?.focus();
    }
  });
  $('#todo-items').appendChild(li);
  input.focus();
}

async function saveComposer() {
  const feed = document.querySelector('input[name="cfeed"]:checked').value;
  const tags = $('#composer-tags').value.split(',').map((s) => s.trim()).filter(Boolean);
  const body = { feed, tags, source: 'web' };
  if (state.composerMode === 'todo') {
    body.type = 'todo';
    body.content = $('#todo-title').value;
    body.todos = [...$('#todo-items').querySelectorAll('li')].map((li) => ({
      text: li.querySelector('input[type="text"]').value,
      checked: li.querySelector('input[type="checkbox"]').checked,
    })).filter((t) => t.text.trim());
  } else {
    body.type = 'note';
    body.content = $('#composer-content').value;
  }
  if (!body.content.trim() && !(body.todos || []).length) return;

  const saved = state.editingNoteId
    ? await api('/api/notes/' + state.editingNoteId, { method: 'PATCH', body: JSON.stringify(body) })
    : await api('/api/notes', { method: 'POST', body: JSON.stringify(body) });

  const remindAt = $('#reminder-at').value;
  if (remindAt && saved) {
    await api('/api/reminders', {
      method: 'POST',
      body: JSON.stringify({
        message: body.content.split('\n')[0].slice(0, 120) || 'Reminder',
        fire_at: remindAt,
        notify_web: $('#reminder-web').checked,
        notify_sms: $('#reminder-sms').checked,
        note_id: saved.id,
      }),
    });
    $('#reminder-at').value = '';
  }
  closeComposer();
  loadTags();
}

function closeComposer() {
  $('#composer-overlay').hidden = true;
  state.editingNoteId = null;
}

// ── Voice ────────────────────────────────────────────────

function setupVoice() {
  if (document.body.dataset.voiceEnabled !== '1') return;
  const btn = $('#voice-btn');
  btn.hidden = false;
  btn.onclick = () => $('#voice-file').click();
  $('#voice-file').onchange = async () => {
    const file = $('#voice-file').files[0];
    if (!file) return;
    btn.textContent = '…';
    const form = new FormData();
    form.append('audio', file);
    const res = await fetch('/api/voice/transcribe', { method: 'POST', body: form });
    const data = await res.json();
    btn.textContent = '🎤';
    if (data.transcript) {
      $('#composer-content').value += (($('#composer-content').value ? '\n' : '') + data.transcript);
      const existing = $('#composer-tags').value.split(',').map((s) => s.trim()).filter(Boolean);
      $('#composer-tags').value = [...new Set([...existing, ...(data.tags || [])])].join(', ');
    } else if (data.error) {
      alert(data.error);
    }
  };
}

// ── Reminders ────────────────────────────────────────────

function showReminderBanner(rem) {
  const dismissed = JSON.parse(sessionStorage.getItem('dismissedReminders') || '[]');
  if (dismissed.includes(rem.id)) return;
  if (document.querySelector(`[data-reminder="${rem.id}"]`)) return;
  const div = document.createElement('div');
  div.className = 'reminder-banner';
  div.dataset.reminder = rem.id;
  div.innerHTML = `⏰ ${escapeHtml(rem.message)} <button>Dismiss</button>`;
  div.querySelector('button').onclick = () => {
    dismissed.push(rem.id);
    sessionStorage.setItem('dismissedReminders', JSON.stringify(dismissed));
    div.remove();
  };
  $('#reminder-banners').appendChild(div);
}

// ── SSE ──────────────────────────────────────────────────

function setupSSE() {
  const evtSource = new EventSource('/api/stream');
  evtSource.onmessage = (e) => {
    const event = JSON.parse(e.data);
    if (event.type === 'heartbeat') return;
    if (event.type === 'reminder') { showReminderBanner(event.data); return; }
    if (['note_created', 'note_updated', 'note_deleted',
         'calendar_event_created', 'calendar_event_updated',
         'calendar_event_orphaned'].includes(event.type)) {
      loadNotes();
      loadTags();
    }
  };
}

// ── Tag management modals (prompt-based, minimal) ────────

const PALETTE = ['#4ade80', '#f87171', '#60a5fa', '#fb923c', '#a78bfa',
                 '#facc15', '#f472b6', '#2dd4bf', '#e5e7eb'];

async function addTagFlow() {
  const name = prompt('Tag name:');
  if (!name) return;
  const color = prompt('Color (hex), or leave blank for default:\n' + PALETTE.join(' ')) || undefined;
  await api('/api/tags', { method: 'POST', body: JSON.stringify({ name, color }) });
  loadTags();
}

async function editTagsFlow() {
  const list = state.tags.map((t) => `${t.id}: #${t.name} (${t.color}, ${t.count} notes)`).join('\n');
  const id = prompt('Tags:\n' + list + '\n\nEnter a tag id to edit, or "d<id>" to delete:');
  if (!id) return;
  if (id.startsWith('d')) {
    await api('/api/tags/' + id.slice(1), { method: 'DELETE' });
  } else {
    const name = prompt('New name (blank to keep):') || undefined;
    const color = prompt('New color hex (blank to keep):') || undefined;
    await api('/api/tags/' + id, { method: 'PATCH', body: JSON.stringify({ name, color }) });
  }
  loadTags();
  loadNotes();
}

// ── Settings (calendar prefs) ────────────────────────────

async function openSettings() {
  $('#settings-overlay').hidden = false;
  const wrap = $('#calendar-prefs');
  wrap.textContent = 'Loading calendars…';
  await api('/api/calendar/calendars'); // triggers discovery
  const prefs = await api('/api/calendar/prefs') || [];
  wrap.innerHTML = prefs.length ? '' : 'No calendars found. Check CalDAV settings in .env.';
  for (const p of prefs) {
    const row = document.createElement('div');
    row.className = 'cal-pref-row';
    row.innerHTML = `<label><input type="checkbox" ${p.enabled ? 'checked' : ''}> ${escapeHtml(p.calendar_name)}</label>` +
      `<select><option value="private" ${p.feed === 'private' ? 'selected' : ''}>Private</option>` +
      `<option value="shared" ${p.feed === 'shared' ? 'selected' : ''}>Shared</option></select>`;
    const update = () => api('/api/calendar/prefs', {
      method: 'PATCH',
      body: JSON.stringify({
        calendar_name: p.calendar_name,
        enabled: row.querySelector('input').checked,
        feed: row.querySelector('select').value,
      }),
    });
    row.querySelector('input').onchange = update;
    row.querySelector('select').onchange = update;
    wrap.appendChild(row);
  }
}

// ── Wiring ───────────────────────────────────────────────

$('#feed-my').onclick = () => {
  state.feed = 'private';
  $('#feed-my').classList.add('active');
  $('#feed-shared').classList.remove('active');
  loadNotes();
};
$('#feed-shared').onclick = () => {
  state.feed = 'shared';
  $('#feed-shared').classList.add('active');
  $('#feed-my').classList.remove('active');
  loadNotes();
};
$('#logout-btn').onclick = async () => {
  await api('/api/auth/logout', { method: 'POST' });
  window.location = '/login';
};
$('#new-note-btn').onclick = () => openComposer(null);
$('#composer-cancel').onclick = closeComposer;
$('#composer-save').onclick = saveComposer;
$('#tab-note').onclick = () => setComposerTab('note');
$('#tab-todo').onclick = () => setComposerTab('todo');
$('#clear-filter-btn').onclick = () => setTagFilter(null);
$('#add-tag-btn').onclick = addTagFlow;
$('#edit-tags-btn').onclick = editTagsFlow;
$('#settings-btn').onclick = openSettings;
$('#settings-close').onclick = () => { $('#settings-overlay').hidden = true; };
$('#sync-now-btn').onclick = async () => {
  $('#sync-status').textContent = 'Syncing…';
  const res = await api('/api/calendar/sync', { method: 'POST' });
  $('#sync-status').textContent = res && res.success
    ? 'Last synced ' + new Date().toLocaleTimeString() : 'Sync failed';
  loadNotes();
};

let searchTimer;
$('#search').addEventListener('input', (e) => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => {
    state.search = e.target.value.trim();
    if (state.search) setTagFilter(null);
    else loadNotes();
    if (state.search) loadNotes();
  }, 250);
});

document.addEventListener('keydown', (e) => {
  const inField = ['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement.tagName);
  if (e.key === 'Escape') {
    closeComposer();
    $('#settings-overlay').hidden = true;
  }
  if (inField) {
    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey) && !$('#composer-overlay').hidden) {
      saveComposer();
    }
    return;
  }
  if (e.key === 'n' || e.key === 'N') { e.preventDefault(); openComposer(null); }
  if (e.key === '/') { e.preventDefault(); $('#search').focus(); }
});

// ── Init ─────────────────────────────────────────────────

loadTags();
loadNotes();
setupSSE();
setupVoice();
api('/api/reminders/pending').then((rems) => (rems || []).forEach(showReminderBanner));
