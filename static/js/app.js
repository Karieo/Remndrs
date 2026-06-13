/* Remndrs web UI — design from the Claude Design handoff wired to the API. */

/* ─── Icon set (inline SVG, no tofu) ───────────────────────── */
const I = {
  sms:'<path d="M21 11.5a8.38 8.38 0 0 1-8.5 8.5 8.5 8.5 0 0 1-3.8-.9L3 21l1.9-5.7A8.5 8.5 0 1 1 21 11.5z"/>',
  voice:'<rect x="9" y="2" width="6" height="11" rx="3"/><path d="M5 10a7 7 0 0 0 14 0M12 17v4"/>',
  email:'<rect x="3" y="5" width="18" height="14" rx="2"/><path d="m3 7 9 6 9-6"/>',
  cal:'<rect x="3" y="4" width="18" height="17" rx="2"/><path d="M3 9h18M8 2v4M16 2v4"/>',
  app:'<rect x="6" y="2" width="12" height="20" rx="3"/><path d="M11 18h2"/>',
  pin:'<path d="M9 4h6l-1 7 3 3v2H7v-2l3-3-1-7z"/><path d="M12 16v5"/>',
  edit:'<path d="M17 3a2.8 2.8 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5z"/>',
  copy:'<rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15V5a2 2 0 0 1 2-2h10"/>',
  send:'<path d="M22 2 11 13M22 2 15 22l-4-9-9-4z"/>',
  trash:'<path d="M3 6h18M8 6V4h8v2M6 6l1 14h10l1-14"/>',
  pinLoc:'<path d="M12 21s7-6 7-11a7 7 0 0 0-14 0c0 5 7 11 7 11z"/><circle cx="12" cy="10" r="2.5"/>',
  link:'<path d="M10 13a5 5 0 0 0 7 0l3-3a5 5 0 0 0-7-7l-1.5 1.5"/><path d="M14 11a5 5 0 0 0-7 0l-3 3a5 5 0 0 0 7 7l1.5-1.5"/>',
  dirIn:'<path d="M19 12H5M11 18l-6-6 6-6"/>',
  dirOut:'<path d="M5 12h14M13 6l6 6-6 6"/>',
  reply:'<path d="M9 17l-5-5 5-5M4 12h11a5 5 0 0 1 5 5v2"/>',
  check:'<path d="M20 6 9 17l-5-5"/>',
  bell:'<path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.7 21a2 2 0 0 1-3.4 0"/>',
  sun:'<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M2 12h2M20 12h2M5 5l1.5 1.5M17.5 17.5 19 19M19 5l-1.5 1.5M6.5 17.5 5 19"/>',
  moon:'<path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/>',
  archive:'<rect x="3" y="4" width="18" height="5" rx="1"/><path d="M5 9v10a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V9M10 13h4"/>',
  clip:'<path d="M21.4 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.2-9.19a4 4 0 0 1 5.65 5.66l-9.19 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"/>',
  spark:'<path d="M12 3v4M12 17v4M3 12h4M17 12h4M5.6 5.6l2.8 2.8M15.6 15.6l2.8 2.8M18.4 5.6l-2.8 2.8M8.4 15.6l-2.8 2.8"/>',
};
const svg = (k,w) => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"${w?` width="${w}" height="${w}"`:''}>${I[k]}</svg>`;

/* ─── Channels ─────────────────────────────────────────────── */
const CH = {
  sms:      { c:'#4ade80', label:'SMS',      ic:'sms'   },
  telegram: { c:'#38bdf8', label:'Telegram', ic:'send'  },
  voice:    { c:'#a78bfa', label:'Voice',    ic:'voice' },
  email:    { c:'#fb923c', label:'Email',    ic:'email' },
  cal:      { c:'#7c6fcd', label:'Calendar', ic:'cal'   },
  claude:   { c:'#d97757', label:'Claude',   ic:'spark' },
  app:      { c:'#c9a96e', label:'App',      ic:'app'   },
};
const DESTS = ['sms','email','cal'];
const noteChan = (n) => ({ sms:'sms', voice:'voice', email:'email', telegram:'telegram', claude:'claude' }[n.source] || 'app');
const PALETTE = ['#4ade80','#f87171','#60a5fa','#fb923c','#a78bfa','#facc15','#f472b6','#2dd4bf','#e5e7eb'];
const AV_COLORS = ['#4ade80','#60a5fa','#fb923c','#a78bfa','#f472b6','#2dd4bf'];

/* ─── State ────────────────────────────────────────────────── */
const ME = { id: document.body.dataset.userId, name: document.body.dataset.userName };
let notes = [], events = [], tags = [], people = [];
let activeFeed = 'private', activeChan = 'all', activeTags = new Set(), search = '';
let previews = {}, openCalNotes = new Set(), openThreads = new Set();
let searchTimer;

const avatarColor = (name) =>
  AV_COLORS[[...String(name)].reduce((a,c)=>a+c.charCodeAt(0),0) % AV_COLORS.length];
const initialsOf = (name) =>
  String(name).split(' ').slice(0,2).map(w=>w[0]||'').join('').toUpperCase() || '?';

async function loadPeople(){ people = (await api('/api/users').catch(()=>[])).filter(u=>u.id!==ME.id); }

/* ─── API helper ───────────────────────────────────────────── */
async function api(path, opts = {}) {
  const res = await fetch(path, { headers: { 'Content-Type': 'application/json' }, ...opts });
  if (res.status === 401) { window.location = '/login'; throw new Error('unauthorized'); }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `Error ${res.status}`);
  return data;
}

const esc = (s) => String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');

// Markdown → HTML, sanitized. Note content arrives from email/SMS/Telegram and
// from other users via the shared feed, so raw HTML in it must never execute.
// If the DOMPurify CDN didn't load, fall back to escaped plain text.
// breaks:true so a single Enter renders as a line break — people type notes
// line by line and expect those returns honored, not collapsed Markdown-style.
if (window.marked) marked.setOptions({ breaks: true, gfm: true });
const md = (s) => window.DOMPurify
  ? DOMPurify.sanitize(marked.parse(s || ''))
  : `<p>${esc(s)}</p>`;

function fmtDate(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  const mon = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'][d.getMonth()];
  let h = d.getHours(), ampm = h >= 12 ? 'PM' : 'AM'; h = h % 12 || 12;
  return `${mon} ${d.getDate()} · ${h}:${String(d.getMinutes()).padStart(2,'0')} ${ampm}`;
}

/* ─── Data loading ─────────────────────────────────────────── */
async function loadTags() { tags = await api('/api/tags'); renderTagBar(); }

async function loadNotes() {
  const params = new URLSearchParams({ feed: activeFeed });
  if (search) params.set('search', search);
  notes = await api('/api/notes?' + params);
  // Calendar events have no archived state — keep the archived view to notes.
  events = (search || activeFeed === 'archived') ? []
    : (await api('/api/calendar/events').catch(() => []));
  renderCards();
}

async function refreshSharedBadge() {
  // Count everything the Shared feed shows: notes plus shared calendar events.
  const [shared, allEvents] = await Promise.all([
    api('/api/notes?feed=shared').catch(() => []),
    api('/api/calendar/events').catch(() => []),
  ]);
  const count = shared.length
    + allEvents.filter(ev => ev.feed === 'shared' && !ev.deleted).length;
  const badge = document.getElementById('sharedBadge');
  badge.textContent = count;
  badge.hidden = !count;
}

/* ─── Render: channel rail ─────────────────────────────────── */
let channelStatus = {};
async function loadChannelStatus(){
  channelStatus = await api('/api/integrations/status').catch(()=>({}));
  renderChanRail();
}
// Show a channel only if its integration is connected — or if notes already
// arrived through it, so a since-disconnected channel still filters its history.
function channelVisible(k){
  if (k === 'app') return true;            // web/iOS always work
  if (channelStatus[k]) return true;
  if (k === 'cal') return events.some(ev => !ev.deleted);
  return notes.some(n => noteChan(n) === k);
}
function renderChanRail() {
  const rail = document.getElementById('chanRail');
  if (activeChan !== 'all' && !channelVisible(activeChan)) activeChan = 'all';
  let html = `<button class="chan-filter all ${activeChan==='all'?'active':''}" onclick="setChan('all')">All</button>`;
  for (const [k,v] of Object.entries(CH)) {
    if (!channelVisible(k)) continue;
    html += `<button class="chan-filter ${activeChan===k?'active':''}" style="--cf:${v.c}" onclick="setChan('${k}')">${svg(v.ic,12)} ${v.label}</button>`;
  }
  rail.innerHTML = html;
}
function setChan(k){ activeChan = k; renderChanRail(); renderCards(); }

/* ─── Render: tag bar ──────────────────────────────────────── */
const TAG_BAR_LIMIT = 9;
function renderTagBar() {
  const bar = document.getElementById('tagBar');
  let html = `<button class="tag-bar-action" onclick="openTagAdd()">+ Add Tag</button><button class="tag-bar-action" onclick="openTagEdit()"># Edit Tags</button><div class="tag-divider"></div>`;
  // Only the most recently-used tags get a pill so the bar stays one or two
  // rows; the full set still lives under "Edit Tags". Active filters always
  // show, even if they've aged out of the recent list.
  const recent = tags.filter(t => t.count)
    .sort((a,b) => String(b.last_used||'').localeCompare(String(a.last_used||'')))
    .slice(0, TAG_BAR_LIMIT);
  const shown = new Set(recent.map(t => t.name));
  for (const name of activeTags) {
    if (!shown.has(name)) {
      const t = tags.find(x => x.name === name);
      if (t) { recent.push(t); shown.add(name); }
    }
  }
  for (const t of recent) {
    html += `<button class="tag-pill ${activeTags.has(t.name)?'active':''}" style="--tag-color:${t.color}" onclick="toggleTag('${esc(t.name)}')">${esc(t.name)}</button>`;
  }
  bar.innerHTML = html;
}
function toggleTag(name){ activeTags.has(name)?activeTags.delete(name):activeTags.add(name); renderTagBar(); renderCards(); }

/* ─── Render: cards ────────────────────────────────────────── */
function tagColor(name) { return (tags.find(t => t.name === name) || {}).color || CH.app.c; }
function accentOf(n) { return n.pinned ? null : (n.tags[0] ? n.tags[0].color : CH.app.c); }

function noteBodyHTML(n) {
  if (n.type === 'todo' && n.todos.length) {
    const done = n.todos.filter(t => t.checked).length, total = n.todos.length;
    return `<div class="todo-title">${esc(n.content.split('\n')[0])}</div>
      <div class="todo-progress-row"><span class="todo-progress-label">${done} / ${total}</span>
      <div class="todo-progress-bar"><div class="todo-progress-fill" style="width:${done/total*100}%"></div></div></div>
      ${n.todos.map(t => `<label class="todo-item" onclick="event.stopPropagation()"><input type="checkbox" ${t.checked?'checked':''} onchange="toggleTodo('${n.id}','${t.id}')"><span class="todo-item-text ${t.checked?'done':''}">${esc(t.text)}</span></label>`).join('')}`;
  }
  let html = `<div class="card-body">${md(n.content)}</div>`;
  const url = (n.content.match(/https?:\/\/[^\s)>\]]+/) || [])[0];
  if (url) html += `<span data-preview-url="${esc(url)}"></span>`;
  return html;
}

function cardHTML(n) {
  const ch = CH[noteChan(n)];
  const chip = `<span class="chan-chip" style="--ch:${ch.c}">${svg(ch.ic)} ${ch.label}</span>`;
  const pin = n.pinned ? `<span class="pin-flag">${svg('pin')} Pinned</span>` : '';
  const tagsRow = n.tags.length ? `<div class="card-tags">${n.tags.map(t=>`<span class="card-tag" style="--tag-color:${t.color}">${esc(t.name)}</span>`).join('')}</div>` : '';
  const shareHead = activeFeed === 'shared' ? sharedHeadHTML(n) : '';
  const header = shareHead || `<div class="card-header">
      <div class="card-meta">${pin}${chip}<span class="card-date">${fmtDate(n.created_at)}</span></div>
      <button class="card-menu" onclick="toggleMenu(event,'${n.id}')">···</button>
    </div>`;
  const outgoing = activeFeed === 'shared' && shareSenderId(n) === ME.id;
  return `<div class="card editable ${n.pinned?'pinned':''} ${shareHead?('shared '+(outgoing?'out':'in')):''}" style="--card-accent:${accentOf(n)||'var(--pinned-border)'}" data-id="${n.id}" onclick="editNote('${n.id}')" title="Click to edit">
    ${header}
    ${tagsRow}
    ${noteBodyHTML(n)}
    ${activeFeed==='shared' ? threadHTML(n) : ''}
    ${dropdownHTML(n)}
  </div>`;
}

const shareSenderId = (n) => n.share ? n.share.sender_id : n.user_id;

function sharedHeadHTML(n) {
  const senderId = shareSenderId(n);
  const senderName = n.share ? n.share.sender_name : (n.user_name || 'Someone');
  const outgoing = senderId === ME.id;
  // Outgoing cards still show who it went to; incoming show who sent it.
  const displayName = outgoing
    ? (n.share ? n.share.recipient_name : 'You') : senderName;
  const color = outgoing && !n.share ? CH.app.c : avatarColor(displayName);
  const dirText = outgoing
    ? (n.share ? `you shared with ${esc(n.share.recipient_name.split(' ')[0])}` : 'you shared')
    : 'shared with you';
  const ch = CH[noteChan(n)];
  return `<div class="share-head">
    <div class="avatar" style="background:${color}">${esc(initialsOf(displayName))}</div>
    <div class="share-who">
      <div class="share-name">${esc(outgoing && !n.share ? 'You' : displayName)}</div>
      <div class="share-ctx">
        <span class="dir" style="--dir:${outgoing?'#7c6fcd':'#4ade80'}">${svg(outgoing?'dirOut':'dirIn')} ${dirText}</span>
        <span>·</span>
        <span class="chan-chip" style="--ch:${ch.c};padding:1px 6px 1px 4px;">${svg(ch.ic)} ${ch.label}</span>
      </div>
    </div>
    <span class="card-date">${fmtDate(n.created_at)}</span>
    <button class="card-menu" onclick="toggleMenu(event,'${n.id}')">···</button>
  </div>`;
}

/* ─── Reply threads ────────────────────────────────────────── */
function replyBubbleHTML(name, userId, text, at) {
  const mine = userId === ME.id;
  const who = mine ? 'You' : String(name).split(' ')[0];
  return `<div class="reply ${mine?'me':''}">
    <div class="avatar" style="background:${mine?CH.app.c:avatarColor(name)}">${esc(initialsOf(mine?ME.name:name))}</div>
    <div><div class="reply-bubble">${esc(text)}</div><div class="reply-meta">${esc(who)} · ${fmtDate(at)}</div></div>
  </div>`;
}

function threadHTML(n) {
  // The share message reads as the opening bubble of the conversation.
  const bubbles = [];
  if (n.share && n.share.message) {
    bubbles.push(replyBubbleHTML(n.share.sender_name, n.share.sender_id,
                                 n.share.message, n.share.created_at));
  }
  for (const r of (n.replies || [])) {
    bubbles.push(replyBubbleHTML(r.user_name, r.user_id, r.text, r.created_at));
  }
  const count = bubbles.length;
  const open = openThreads.has(n.id);
  const thread = open && count
    ? `<div class="thread">${bubbles.join('')}</div>`
    : (count ? `<button class="thread-toggle" onclick="event.stopPropagation();toggleThread('${n.id}')">${svg('reply')} ${count} ${count===1?'reply':'replies'} · view</button>` : '');
  const who = shareSenderId(n) === ME.id
    ? (n.share ? n.share.recipient_name.split(' ')[0] : 'them')
    : (n.share ? n.share.sender_name.split(' ')[0] : (n.user_name||'them').split(' ')[0]);
  return `${thread}
    <div class="reply-input-row">
      <input class="reply-input" id="reply-${n.id}" placeholder="Reply to ${esc(who)}…"
        onclick="event.stopPropagation()"
        onkeydown="if(event.key==='Enter')sendReply('${n.id}')">
      <button class="reply-send" onclick="event.stopPropagation();sendReply('${n.id}')" title="Send reply">${svg('send')}</button>
    </div>`;
}

function toggleThread(id){ openThreads.has(id)?openThreads.delete(id):openThreads.add(id); renderCards(); }

async function sendReply(id){
  const input = document.getElementById('reply-'+id);
  const text = input.value.trim();
  if (!text) return;
  try {
    await api(`/api/notes/${id}/replies`, { method:'POST', body: JSON.stringify({ text }) });
    openThreads.add(id);
    const n = notes.find(x=>x.id===id);
    const who = n && n.share
      ? (n.share.sender_id===ME.id ? n.share.recipient_name : n.share.sender_name).split(' ')[0]
      : 'them';
    toast(`${svg('reply',13)} Reply sent to ${esc(who)}`);
    loadNotes();
  } catch (e) { toast(esc(e.message)); }
}

/* ─── Share with a person ──────────────────────────────────── */
let shareNoteId = null, sharePerson = null;
function openShare(id){
  closeAllMenus();
  shareNoteId = id;
  sharePerson = people.length === 1 ? people[0].id : null;
  const n = notes.find(x=>x.id===id);
  document.getElementById('shareQuote').textContent = (n.content||'').replace(/[#*`>\[\]]/g,' ').trim().slice(0,140);
  document.getElementById('shareMsg').value = '';
  renderPeopleGrid();
  document.getElementById('shareOverlay').classList.add('open');
}
function renderPeopleGrid(){
  document.getElementById('peopleGrid').innerHTML = people.length ? people.map(p=>
    `<div class="person-opt ${sharePerson===p.id?'sel':''}" onclick="pickPerson('${p.id}')">
      <div class="avatar" style="background:${avatarColor(p.name)}">${esc(initialsOf(p.name))}</div>
      <span class="pname">${esc(p.name)}</span>
      <span class="pcheck">${svg('check')}</span>
    </div>`).join('')
    : '<div class="grid-empty">No one else here yet — add a second user on the Mac first.</div>';
}
function pickPerson(id){ sharePerson = id; renderPeopleGrid(); }
function closeShare(){ document.getElementById('shareOverlay').classList.remove('open'); }
async function confirmShare(){
  if (!sharePerson){ toast('Pick someone first'); return; }
  const message = document.getElementById('shareMsg').value.trim();
  try {
    await api(`/api/notes/${shareNoteId}/share`, { method:'POST',
      body: JSON.stringify({ recipient_id: sharePerson, message }) });
    const name = (people.find(p=>p.id===sharePerson)||{}).name || '';
    closeShare();
    toast(`${svg('check',13)} Shared with ${esc(name.split(' ')[0])}`);
    loadNotes(); refreshSharedBadge();
  } catch (e) { toast(esc(e.message)); }
}

function eventCardHTML(ev) {
  const past = new Date(ev.end_at) < new Date();
  const time = ev.all_day ? 'All day'
    : `${fmtTime(ev.start_at)} – ${fmtTime(ev.end_at)}`;
  const meta = [ev.location, time].filter(Boolean).join(' <span>·</span> ');
  const notesBlock = `<div id="calNotes-${ev.id}"></div>`;
  const input = openCalNotes.has(ev.id)
    ? `<textarea class="cal-note-input" id="calIn-${ev.id}" placeholder="Note (never touches the event)…" onkeydown="if((event.metaKey||event.ctrlKey)&&event.key==='Enter')saveCalNote('${ev.id}')"></textarea>
       <button class="cal-add" onclick="saveCalNote('${ev.id}')">Save note</button>`
    : `<button class="cal-add" onclick="openCalNote('${ev.id}')">+ Add note to this event</button>`;
  return `<div class="card ${past?'past-event':''}" style="--card-accent:${ev.deleted?'#f97316':CH.cal.c}" data-event="${ev.id}">
    <div class="card-header">
      <div class="card-meta">
        <span class="chan-chip" style="--ch:${CH.cal.c}">${svg('cal')} ${esc(ev.calendar_name)}</span>
        ${ev.deleted?'<span class="pin-flag" style="color:#f97316;border-color:#f97316;">Orphaned</span>':''}
        <span class="card-date">${fmtDate(ev.start_at)}</span>
      </div>
    </div>
    <div class="cal-title">${esc(ev.title)}</div>
    <div class="cal-meta">${svg('pinLoc')} ${meta}</div>
    ${notesBlock}${input}
  </div>`;
}
function fmtTime(iso){ const d=new Date(iso); let h=d.getHours(),ap=h>=12?'PM':'AM'; h=h%12||12; return `${h}:${String(d.getMinutes()).padStart(2,'0')} ${ap}`; }

/* ─── B3 · Send menu dropdown ──────────────────────────────── */
function dropdownHTML(n) {
  const sendItems = DESTS.map(d=>{
    const v = CH[d];
    const verb = d==='cal' ? 'Add to Calendar' : `Send via ${v.label}`;
    return `<div class="dd-item" style="--c:${v.c}" onclick="openSheet('${n.id}','${d}')"><span class="di">${svg(v.ic)}</span> ${verb}</div>`;
  }).join('');
  const moveLabel = n.feed === 'shared' ? 'Move to Mine' : 'Move to Shared';
  return `<div class="dropdown" id="dd-${n.id}" onclick="event.stopPropagation()">
    <div class="dd-item" onclick="editNote('${n.id}')"><span class="di" style="--c:var(--accent)">${svg('edit')}</span> Edit note & tags</div>
    <div class="dd-sep"></div>
    <div class="dd-label">Send to</div>
    ${sendItems}
    <div class="dd-sep"></div>
    <div class="dd-item" style="--c:#60a5fa" onclick="openShare('${n.id}')"><span class="di">${svg('reply')}</span> Share with…</div>
    <div class="dd-item" onclick="moveFeed('${n.id}')"><span class="di">${svg('dirOut')}</span> ${moveLabel}</div>
    <div class="dd-item" onclick="copyNote('${n.id}')"><span class="di">${svg('copy')}</span> Copy text</div>
    <div class="dd-item" onclick="togglePin('${n.id}')"><span class="di">${svg('pin')}</span> ${n.pinned?'Unpin':'Pin to top'}</div>
    <div class="dd-item" onclick="archiveNote('${n.id}', ${n.archived?'false':'true'})"><span class="di">${svg('archive')}</span> ${n.archived?'Restore':'Archive'}</div>
    <div class="dd-item" onclick="deleteNote('${n.id}')"><span class="di">${svg('trash')}</span> Delete</div>
  </div>`;
}

/* ─── Render feed ──────────────────────────────────────────── */
function visibleNotes() {
  return notes.filter(n => {
    if (activeChan !== 'all' && activeChan !== 'cal' && noteChan(n) !== activeChan) return false;
    if (activeChan === 'cal') return false;
    if (activeTags.size && !n.tags.some(t => activeTags.has(t.name))) return false;
    return true;
  });
}

function visibleEvents() {
  if (activeChan !== 'all' && activeChan !== 'cal') return [];
  if (activeTags.size || search) return [];
  return events.filter(ev => ev.feed === activeFeed && !ev.deleted);
}

function renderCards() {
  const grid = document.getElementById('grid');
  const items = [
    ...visibleNotes().map(n => ({ pinned: n.pinned, at: n.created_at, html: () => cardHTML(n) })),
    ...visibleEvents().map(ev => ({ pinned: false, at: ev.start_at, html: () => eventCardHTML(ev) })),
  ].sort((a,b) => (b.pinned?1:0)-(a.pinned?1:0) || String(b.at).localeCompare(String(a.at)));
  grid.innerHTML = items.length ? items.map(i => i.html()).join('')
    : `<div class="grid-empty">No ${activeFeed==='archived'?'archived ':activeFeed==='shared'?'shared ':''}notes match.</div>`;
  renderChanRail();   // notes/events just changed — a channel may now (dis)appear
  hydrateLinkPreviews();
  visibleEvents().forEach(ev => loadCalNotes(ev.id));
}

function hydrateLinkPreviews() {
  document.querySelectorAll('[data-preview-url]').forEach(async (el) => {
    const url = el.dataset.previewUrl;
    if (!previews[url]) {
      // Cache the promise, not the result: re-renders while a fetch is in
      // flight (SSE refreshes, several cards with the same link) would
      // otherwise each fire their own request for the same URL.
      previews[url] = fetch('/api/preview?url='+encodeURIComponent(url)).then(r=>r.json()).catch(()=>({}));
    }
    const p = await previews[url];
    if (!p || !p.title) return;
    el.outerHTML = `<a class="link-preview" href="${esc(url)}" target="_blank" rel="noopener" onclick="event.stopPropagation()">
      <div class="link-preview-img">${p.image?`<img src="${esc(p.image)}" alt="">`:svg('link')}</div>
      <div class="link-preview-text">
        ${p.site_name?`<div class="link-preview-site">${esc(p.site_name)}</div>`:''}
        <div class="link-preview-title">${esc(p.title)}</div>
      </div></a>`;
  });
}

/* ─── Calendar event notes ─────────────────────────────────── */
async function loadCalNotes(eventId) {
  const wrap = document.getElementById('calNotes-'+eventId);
  if (!wrap) return;
  const full = await api('/api/calendar/events/'+eventId).catch(() => null);
  if (!full || !full.notes || !full.notes.length) return;
  wrap.innerHTML = full.notes.map(n => `<div class="cal-note card-body">${md(n.content)}</div>`).join('');
}
function openCalNote(id){ openCalNotes.add(id); renderCards(); setTimeout(()=>document.getElementById('calIn-'+id)?.focus(),50); }
async function saveCalNote(id) {
  const input = document.getElementById('calIn-'+id);
  const content = input.value.trim();
  openCalNotes.delete(id);
  if (content) {
    await api('/api/calendar/notes', { method:'POST', body: JSON.stringify({ event_id:id, content }) }).catch(e=>toast(esc(e.message)));
    toast(`${svg('check',13)} Note added to event`);
  }
  renderCards();
}

/* ─── Feed / search ────────────────────────────────────────── */
function setFeed(f){
  activeFeed = f;
  document.getElementById('feedMine').classList.toggle('active', f==='private');
  document.getElementById('feedShared').classList.toggle('active', f==='shared');
  document.getElementById('feedArchived').classList.toggle('active', f==='archived');
  document.getElementById('search').placeholder =
    f==='archived' ? 'Search archived notes…' :
    f==='shared'   ? 'Search shared notes…' : 'Search by text or date…';
  closeAllMenus();
  loadNotes();
}
function onSearchInput(){
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => { search = document.getElementById('search').value.trim(); loadNotes(); }, 250);
}

/* ─── Menus ────────────────────────────────────────────────── */
function closeAllMenus(){
  document.querySelectorAll('.dropdown.open').forEach(d=>d.classList.remove('open'));
  document.querySelectorAll('.card-menu.open').forEach(b=>b.classList.remove('open'));
  document.querySelectorAll('.card.menu-open').forEach(c=>c.classList.remove('menu-open'));
}
function toggleMenu(e,id){
  e.stopPropagation();
  const dd = document.getElementById('dd-'+id);
  const wasOpen = dd.classList.contains('open');
  closeAllMenus();
  if (!wasOpen){
    dd.classList.add('open');
    e.currentTarget.classList.add('open');
    // Lift the whole card above its neighbours; in the masonry columns a
    // plain z-index on the menu still paints under the next card down.
    dd.closest('.card')?.classList.add('menu-open');
  }
}
document.addEventListener('click', closeAllMenus);

/* ─── B4 · Send sheet ──────────────────────────────────────── */
let sheetNote = null, sheetDest = 'sms', calendarPrefs = null;
async function openSheet(id, dest){
  closeAllMenus();
  sheetNote = notes.find(n=>n.id===id);
  if (!sheetNote) return;
  sheetDest = dest || 'sms';
  const q = (sheetNote.content||'').replace(/[#*`>\[\]]/g,' ').trim();
  document.getElementById('sheetQuote').textContent = q.slice(0,140);
  if (!calendarPrefs) calendarPrefs = (await api('/api/calendar/prefs').catch(()=>[])).filter(p=>p.enabled);
  renderDestRow();
  document.getElementById('sendOverlay').classList.add('open');
}
function renderDestRow(){
  document.getElementById('destRow').innerHTML = DESTS.map(d=>{
    const v = CH[d];
    return `<div class="dest-opt ${sheetDest===d?'sel':''}" style="--c:${v.c}" onclick="pickDest('${d}')">${svg(v.ic)}<div class="dn">${v.label}</div></div>`;
  }).join('');
  const f = document.getElementById('destField'), lbl = document.getElementById('fieldLabel');
  const calWrap = document.getElementById('calFieldWrap');
  calWrap.hidden = sheetDest !== 'cal';
  if (sheetDest==='sms'){ lbl.textContent='To'; f.type='text'; f.value=''; f.placeholder='Phone (blank = your number)'; }
  else if (sheetDest==='email'){ lbl.textContent='To'; f.type='text'; f.value=''; f.placeholder='Email (blank = your address)'; }
  else {
    lbl.textContent='When'; f.type='datetime-local';
    const d = new Date(Date.now()+3600e3); d.setMinutes(0,0,0);
    f.value = `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}T${String(d.getHours()).padStart(2,'0')}:00`;
    document.getElementById('calSelect').innerHTML = calendarPrefs.length
      ? calendarPrefs.map(p=>`<option value="${esc(p.calendar_name)}">${esc(p.calendar_name)}</option>`).join('')
      : '<option value="">No calendars enabled</option>';
  }
  document.getElementById('sendGo').textContent = sheetDest==='cal' ? 'Add →' : 'Send →';
}
function pickDest(d){ sheetDest=d; renderDestRow(); }
function closeSheet(){ document.getElementById('sendOverlay').classList.remove('open'); }
async function confirmSend(){
  if (!sheetNote) return;
  const f = document.getElementById('destField');
  try {
    if (sheetDest === 'cal') {
      const calendar = document.getElementById('calSelect').value;
      if (!calendar) { toast('Enable a calendar in settings first'); return; }
      const start = new Date(f.value);
      const end = new Date(start.getTime()+3600e3);
      const iso = (d)=>`${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}T${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}:00`;
      await api(`/api/notes/${sheetNote.id}/to-event`, { method:'POST',
        body: JSON.stringify({ calendar_name:calendar, start_at:iso(start), end_at:iso(end), all_day:false }) });
      toast(`${svg('cal',13)} Added to ${esc(calendar)}`);
    } else {
      await api(`/api/notes/${sheetNote.id}/send`, { method:'POST',
        body: JSON.stringify({ channel: sheetDest, to: f.value.trim() }) });
      toast(`${svg(CH[sheetDest].ic,13)} Sent via ${CH[sheetDest].label}`);
    }
    closeSheet();
  } catch (e) { toast(esc(e.message)); }
}

/* ─── Card quick actions ───────────────────────────────────── */
async function copyNote(id){
  closeAllMenus();
  const n = notes.find(x=>x.id===id);
  if (!n) return;
  // A to-do note's content is only its title — the items live in n.todos, so
  // copying content alone lost the whole list. Rebuild the full text here.
  let text = n.content || '';
  if (n.type === 'todo' && n.todos && n.todos.length) {
    text = [n.content, ...n.todos.map(t => `${t.checked ? '[x]' : '[ ]'} ${t.text}`)]
      .filter(Boolean).join('\n');
  }
  if (navigator.clipboard) navigator.clipboard.writeText(text).catch(()=>{});
  toast(`${svg('copy',13)} Copied to clipboard`);
}
async function togglePin(id){
  closeAllMenus();
  const n = notes.find(x=>x.id===id);
  await api('/api/notes/'+id, { method:'PATCH', body: JSON.stringify({ pinned: !n.pinned }) });
  toast(`${svg('pin',13)} ${!n.pinned?'Pinned to top':'Unpinned'}`);
  loadNotes();
}
async function moveFeed(id){
  closeAllMenus();
  const n = notes.find(x=>x.id===id);
  const to = n.feed === 'shared' ? 'private' : 'shared';
  await api('/api/notes/'+id, { method:'PATCH', body: JSON.stringify({ feed: to }) });
  toast(`${svg('reply',13)} Moved to ${to==='shared'?'Shared':'Mine'}`);
  loadNotes(); refreshSharedBadge();
}
async function archiveNote(id, archived){
  closeAllMenus();
  await api('/api/notes/'+id, { method:'PATCH', body: JSON.stringify({ archived }) });
  toast(`${svg('archive',13)} ${archived ? 'Archived' : 'Restored'}`);
  loadNotes(); refreshSharedBadge();
}
async function deleteNote(id){
  closeAllMenus();
  if (!confirm('Delete this note? The .md file goes too.')) return;
  await api('/api/notes/'+id, { method:'DELETE' });
  toast(`${svg('trash',13)} Deleted`);
  loadNotes(); refreshSharedBadge();
}
async function toggleTodo(noteId, todoId){
  const n = notes.find(x=>x.id===noteId);
  const todos = n.todos.map(t => ({ text:t.text, checked: t.id===todoId ? !t.checked : t.checked }));
  await api('/api/notes/'+noteId, { method:'PATCH', body: JSON.stringify({ todos }) });
  loadNotes();
}

/* ─── Tag management ───────────────────────────────────────── */
let tagAddColor = PALETTE[0];
function openTagAdd(){
  tagAddColor = PALETTE[tags.length % PALETTE.length];
  document.getElementById('tagAddName').value = '';
  renderSwatches();
  document.getElementById('tagAddOverlay').classList.add('open');
  setTimeout(()=>document.getElementById('tagAddName').focus(),50);
}
function renderSwatches(){
  document.getElementById('tagAddSwatches').innerHTML = PALETTE.map(c=>
    `<div class="swatch ${tagAddColor===c?'sel':''}" style="background:${c}" onclick="tagAddColor='${c}';renderSwatches()"></div>`).join('');
}
function closeTagAdd(){ document.getElementById('tagAddOverlay').classList.remove('open'); }
async function confirmTagAdd(){
  const name = document.getElementById('tagAddName').value.trim();
  if (!name) return;
  await api('/api/tags', { method:'POST', body: JSON.stringify({ name, color: tagAddColor }) }).catch(e=>toast(esc(e.message)));
  closeTagAdd();
  await loadTags();
  toast(`${svg('check',13)} Tag added`);
}

function openTagEdit(){
  renderTagEditList();
  document.getElementById('tagEditOverlay').classList.add('open');
}
function renderTagEditList(){
  document.getElementById('tagEditList').innerHTML = tags.length ? tags.map(t=>
    `<div class="tag-edit-row">
      <div class="dot" style="background:${t.color}" title="Click to recolour" onclick="cycleTagColor(${t.id})"></div>
      <input value="${esc(t.name)}" onchange="renameTag(${t.id}, this.value)">
      <span class="tcount">${t.count} note${t.count===1?'':'s'}</span>
      <button class="tdel" title="Delete tag" onclick="deleteTag(${t.id})">${svg('trash',12)}</button>
    </div>`).join('') : '<div class="grid-empty">No tags yet.</div>';
}
function closeTagEdit(){ document.getElementById('tagEditOverlay').classList.remove('open'); loadNotes(); }
async function cycleTagColor(id){
  const t = tags.find(x=>x.id===id);
  const next = PALETTE[(PALETTE.indexOf(t.color)+1+PALETTE.length) % PALETTE.length];
  await api('/api/tags/'+id, { method:'PATCH', body: JSON.stringify({ color: next }) });
  await loadTags(); renderTagEditList();
}
async function renameTag(id, name){
  if (!name.trim()) return;
  await api('/api/tags/'+id, { method:'PATCH', body: JSON.stringify({ name }) }).catch(e=>toast(esc(e.message)));
  await loadTags(); renderTagEditList();
}
async function deleteTag(id){
  await api('/api/tags/'+id, { method:'DELETE' });
  await loadTags(); renderTagEditList();
}

/* ─── Settings ─────────────────────────────────────────────── */
let settingsTab = 'integrations';
let settingsData = null;   // null when not owner

function openSettings(){
  document.getElementById('settingsOverlay').classList.add('open');
  renderSettings();
}
function closeSettings(){ document.getElementById('settingsOverlay').classList.remove('open'); }

async function renderSettings(){
  settingsData = await api('/api/settings').catch(()=>null);
  const tabs = settingsData
    ? [['integrations','Integrations'],['people','People'],['webhooks','Webhooks'],['calendars','Calendars']]
    : [['people','People'],['calendars','Calendars']];
  if (!tabs.some(t=>t[0]===settingsTab)) settingsTab = tabs[0][0];
  document.getElementById('settingsNav').innerHTML = tabs.map(([k,label])=>
    `<button class="${settingsTab===k?'active':''}" onclick="setSettingsTab('${k}')">${label}</button>`).join('');
  const body = document.getElementById('settingsBody');
  if (settingsTab === 'integrations') renderIntegrations(body);
  else if (settingsTab === 'people') renderPeopleSettings(body);
  else if (settingsTab === 'webhooks') renderWebhooks(body);
  else renderCalendarSettings(body);
}
function setSettingsTab(tab){ settingsTab = tab; renderSettings(); }

/* — Integrations — */
const SERVICES = [
  { id:'claude', title:'Claude', status:'claude', connect:true,
    sub:'Talk to Claude anywhere and it can save notes, set reminders, and search your notes. Set your Public URL (Webhooks tab), click Connect, then paste the URL into <a href="https://claude.ai/settings/connectors" target="_blank">claude.ai → Settings → Connectors</a> → Add custom connector. Reconnecting revokes the old URL.',
    fields:[] },
  { id:'telegram', title:'Telegram', status:'telegram', connect:true,
    sub:'Free, instant, no carrier registration. Make a bot with <a href="https://t.me/BotFather" target="_blank">@BotFather</a>, paste its token, Save, then Connect. Then message your bot and it tells you how to link.',
    fields:[['TELEGRAM_BOT_TOKEN','Bot token (from @BotFather)']] },
  { id:'twilio', title:'Texts & calls', status:'sms',
    sub:'Twilio — text or call your own number to capture. Note: US SMS needs carrier registration. <a href="https://console.twilio.com" target="_blank">console.twilio.com</a>',
    fields:[['TWILIO_ACCOUNT_SID','Account SID'],['TWILIO_AUTH_TOKEN','Auth token'],['OWNER_PHONE_NUMBER','Your mobile number (for replies & reminders)']] },
  { id:'openai', title:'Voice transcription', status:'voice_transcription',
    sub:'OpenAI Whisper — turns voice memos and phone calls into notes.',
    fields:[['OPENAI_API_KEY','API key']] },
  { id:'mailgun', title:'Email', status:'email_in',
    sub:'Mailgun — forward emails in, send notes out. Needs a domain.',
    fields:[['MAILGUN_API_KEY','API key'],['MAILGUN_SIGNING_KEY','Webhook signing key'],['MAILGUN_INBOUND_ADDRESS','Inbound address (notes@yourdomain.com)']] },
  { id:'caldav', title:'iCloud Calendar', status:'calendar',
    sub:'Use an <a href="https://appleid.apple.com" target="_blank">app-specific password</a> — never your real Apple ID password.',
    fields:[['CALDAV_USERNAME','Apple ID email'],['CALDAV_PASSWORD','App-specific password']] },
];
const SECRET_KEYS = new Set(['TWILIO_AUTH_TOKEN','OPENAI_API_KEY','MAILGUN_API_KEY','MAILGUN_SIGNING_KEY','CALDAV_PASSWORD','TELEGRAM_BOT_TOKEN']);

function renderIntegrations(body){
  body.innerHTML = SERVICES.map(svc => {
    const on = settingsData.status[svc.status];
    const fields = svc.fields.map(([key,label]) => {
      const entry = settingsData[key] || {};
      const secret = SECRET_KEYS.has(key);
      const placeholder = secret ? (entry.set ? '•••••• (saved — type to replace)' : label) : label;
      const value = secret ? '' : (entry.value || '');
      return `<div class="set-row"><div class="field" style="margin:0">
        <input id="env-${key}" type="${secret?'password':'text'}" placeholder="${esc(placeholder)}" value="${esc(value)}" autocomplete="off">
      </div></div>`;
    }).join('');
    return `<div class="set-section">
      <div class="set-h"><span class="set-status ${on?'on':''}"></span>${svc.title}</div>
      <div class="set-sub">${svc.sub}</div>
      ${fields}
      <div class="set-test">
        ${svc.fields.length ? `<button class="sx" onclick="saveService('${svc.id}')">Save</button>` : ''}
        ${svc.connect ? `<button class="sx" onclick="connectService('${svc.id}')">Connect</button>` : ''}
        <button class="sx" onclick="testService('${svc.id}')">Test</button>
        <span class="set-test-result" id="test-${svc.id}"></span>
      </div>
    </div><div class="set-divider"></div>`;
  }).join('') + `<div class="set-sub">Saved settings apply immediately — no restart needed. They're stored in the app's .env file on your Mac.</div>`;
}

async function saveService(serviceId){
  const svc = SERVICES.find(s=>s.id===serviceId);
  const updates = {};
  for (const [key] of svc.fields) {
    const value = document.getElementById('env-'+key).value.trim();
    if (value) updates[key] = value;
  }
  const out = document.getElementById('test-'+serviceId);
  if (!Object.keys(updates).length) { out.textContent = 'nothing to save'; return; }
  await api('/api/settings', { method:'PATCH', body: JSON.stringify(updates) });
  out.className = 'set-test-result ok';
  out.textContent = 'saved ✓';
  settingsData = await api('/api/settings').catch(()=>settingsData);
}
async function connectService(serviceId){
  const out = document.getElementById('test-'+serviceId);
  out.className = 'set-test-result';
  out.textContent = 'connecting…';
  const res = await api('/api/settings/'+serviceId+'/connect', { method:'POST' })
    .catch(e=>({ok:false, detail:e.message}));
  out.className = 'set-test-result ' + (res.ok ? 'ok' : 'bad');
  out.textContent = res.detail || (res.ok ? 'connected ✓' : 'failed');
  if (res.ok && res.url){
    // The token inside is stored hashed server-side — this is the one chance
    // to copy the URL, so surface it as a copyable row right here.
    const row = document.createElement('div');
    row.className = 'set-row connect-url-row';
    row.innerHTML = `<div class="field" style="margin:0">
        <input value="${esc(res.url)}" readonly onclick="this.select()">
      </div><button class="sx" onclick="copyText('${esc(res.url)}')">Copy</button>`;
    out.closest('.set-section').querySelector('.connect-url-row')?.remove();
    out.closest('.set-test').before(row);
  }
}
async function testService(serviceId){
  const out = document.getElementById('test-'+serviceId);
  out.className = 'set-test-result';
  out.textContent = 'testing…';
  const res = await api('/api/settings/test/'+serviceId, { method:'POST' }).catch(e=>({ok:false, detail:e.message}));
  out.className = 'set-test-result ' + (res.ok ? 'ok' : 'bad');
  out.textContent = res.detail || (res.ok ? 'OK' : 'failed');
}

/* — People — */
async function renderPeopleSettings(body){
  const me = await api('/api/users/me');
  const everyone = await api('/api/users');
  const isOwner = me.role === 'owner';
  body.innerHTML = `
    <div class="set-section">
      <div class="set-h">You — ${esc(me.name)}</div>
      <div class="set-sub">Where your capture channels route. Email = the address you send notes from/to; Remndrs number = your dedicated Twilio number.</div>
      <div class="set-row"><div class="field" style="margin:0"><span>Email</span><input id="me-email" value="${esc(me.email||'')}" placeholder="notes@yourdomain.com"></div></div>
      <div class="set-row"><div class="field" style="margin:0"><span>Mobile</span><input id="me-phone" value="${esc(me.phone_number||'')}" placeholder="+1 555 123 4567"></div></div>
      <div class="set-row"><div class="field" style="margin:0"><span>Remndrs #</span><input id="me-twilio" value="${esc(me.twilio_number||'')}" placeholder="+1 555 000 0000 (your Twilio number)"></div></div>
      <div class="set-row"><div class="field" style="margin:0"><span>Telegram</span><input id="me-telegram" value="${esc(me.telegram_chat_id||'')}" placeholder="chat ID — message your bot, it replies with this"></div></div>
      <div class="set-test"><button class="sx" onclick="saveMe()">Save</button><span class="set-test-result" id="me-result"></span></div>
    </div>
    <div class="set-divider"></div>
    <div class="set-section">
      <div class="set-h">Everyone</div>
      <div class="set-sub">${everyone.map(u=>esc(u.name)).join(' · ')}</div>
      ${isOwner ? `
      <div class="set-sub" style="margin-top:10px">Add a person — they get their own private feed and can share with you:</div>
      <div class="set-row"><div class="field" style="margin:0"><span>Name</span><input id="new-name"></div></div>
      <div class="set-row"><div class="field" style="margin:0"><span>Password</span><input id="new-pass" type="password"></div></div>
      <div class="set-row"><div class="field" style="margin:0"><span>Email</span><input id="new-email" placeholder="optional — their inbound address"></div></div>
      <div class="set-test"><button class="sx" onclick="addPerson()">Add person</button><span class="set-test-result" id="add-result"></span></div>
      ` : ''}
    </div>`;
}
async function saveMe(){
  const out = document.getElementById('me-result');
  await api('/api/users/me', { method:'PATCH', body: JSON.stringify({
    email: document.getElementById('me-email').value,
    phone_number: document.getElementById('me-phone').value,
    twilio_number: document.getElementById('me-twilio').value,
    telegram_chat_id: document.getElementById('me-telegram').value,
  })}).then(()=>{ out.className='set-test-result ok'; out.textContent='saved ✓'; })
    .catch(e=>{ out.className='set-test-result bad'; out.textContent=e.message; });
}
async function addPerson(){
  const out = document.getElementById('add-result');
  await api('/api/users', { method:'POST', body: JSON.stringify({
    name: document.getElementById('new-name').value,
    password: document.getElementById('new-pass').value,
    email: document.getElementById('new-email').value,
  })}).then(u=>{ out.className='set-test-result ok'; out.textContent=`${u.name} added ✓`; loadPeople(); renderPeopleSettings(document.getElementById('settingsBody')); })
    .catch(e=>{ out.className='set-test-result bad'; out.textContent=e.message; });
}

/* — Webhooks — */
function renderWebhooks(body){
  const publicURL = (settingsData.PUBLIC_URL && settingsData.PUBLIC_URL.value || '').replace(/\/$/,'');
  const base = publicURL || 'https://your-tunnel-url';
  body.innerHTML = `
    <div class="set-section">
      <div class="set-h">Public URL</div>
      <div class="set-sub">Your Cloudflare Tunnel address (see CLOUDFLARE_SETUP.md). Saving it fills in the webhook URLs below — paste those into the Twilio / Mailgun consoles.</div>
      <div class="set-row"><div class="field" style="margin:0"><input id="env-PUBLIC_URL" value="${esc(publicURL)}" placeholder="https://remndrs.yourdomain.com"></div></div>
      <div class="set-test"><button class="sx" onclick="savePublicURL()">Save</button><span class="set-test-result" id="url-result"></span></div>
    </div>
    <div class="set-divider"></div>
    <div class="set-section">
      <div class="set-h">Paste these into the provider consoles</div>
      <div class="set-sub" style="margin-bottom:10px">Twilio: number settings. Mailgun: Receiving → Routes.</div>
      ${[['SMS', '/webhooks/sms'], ['Call answer', '/webhooks/voice/answer'],
         ['Call audio', '/webhooks/voice'], ['Email', '/webhooks/email']].map(([label, path])=>
        `<div class="webhook-row"><span class="wlabel">${label}</span><code>${esc(base+path)}</code>
         <button class="sx" onclick="copyText('${esc(base+path)}')">Copy</button></div>`).join('')}
    </div>`;
}
async function savePublicURL(){
  const out = document.getElementById('url-result');
  const value = document.getElementById('env-PUBLIC_URL').value.trim();
  await api('/api/settings', { method:'PATCH', body: JSON.stringify({ PUBLIC_URL: value }) });
  out.className='set-test-result ok'; out.textContent='saved ✓';
  settingsData = await api('/api/settings');
  renderWebhooks(document.getElementById('settingsBody'));
}
function copyText(text){
  if (navigator.clipboard) navigator.clipboard.writeText(text).catch(()=>{});
  toast(`${svg('copy',13)} Copied`);
}

/* — Calendars — */
async function renderCalendarSettings(body){
  body.innerHTML = `<div class="set-section">
    <div class="set-h">Calendars</div>
    <div class="set-sub">Enable iCloud calendars and pick their feed</div>
    <div class="pref-list" id="prefList">Looking for calendars…</div>
    <div class="set-test"><button class="sx" onclick="syncNow()">Sync now</button><span class="set-test-result" id="syncStatus"></span></div>
  </div>`;
  await api('/api/calendar/calendars').catch(()=>[]);  // triggers discovery
  const prefs = await api('/api/calendar/prefs').catch(()=>[]);
  calendarPrefs = null; // invalidate send-sheet cache
  const list = document.getElementById('prefList');
  if (!list) return;
  list.innerHTML = prefs.length ? prefs.map(p=>
    `<div class="pref-row">
      <input type="checkbox" ${p.enabled?'checked':''} onchange="setPref('${esc(p.calendar_name)}', this.checked, null)">
      <span class="pname">${esc(p.calendar_name)}</span>
      <select onchange="setPref('${esc(p.calendar_name)}', null, this.value)">
        <option value="private" ${p.feed==='private'?'selected':''}>Private</option>
        <option value="shared" ${p.feed==='shared'?'selected':''}>Shared</option>
      </select>
    </div>`).join('')
    : '<div class="grid-empty">No calendars found — add your Apple ID under Integrations → iCloud Calendar first.</div>';
}
async function setPref(name, enabled, feed){
  const body = { calendar_name: name };
  if (enabled !== null) body.enabled = enabled;
  if (feed !== null) body.feed = feed;
  await api('/api/calendar/prefs', { method:'PATCH', body: JSON.stringify(body) });
}
async function syncNow(){
  const el = document.getElementById('syncStatus');
  el.textContent = 'Syncing…';
  const res = await api('/api/calendar/sync', { method:'POST' }).catch(e=>({error:e.message}));
  el.className = 'set-test-result ' + (res.error ? 'bad' : 'ok');
  el.textContent = res.error ? 'Sync failed' : 'Synced just now';
  loadNotes();
}

/* ─── Toast ────────────────────────────────────────────────── */
let toastTimer;
function toast(html){
  const t = document.getElementById('toast');
  t.innerHTML = html;
  t.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(()=>t.classList.remove('show'), 2200);
}

/* ─── Reminder banners ─────────────────────────────────────── */
function showReminderBanner(rem){
  const dismissed = JSON.parse(sessionStorage.getItem('dismissedReminders') || '[]');
  if (dismissed.includes(rem.id) || document.querySelector(`[data-reminder="${rem.id}"]`)) return;
  const div = document.createElement('div');
  div.className = 'reminder-banner';
  div.dataset.reminder = rem.id;
  div.innerHTML = `<span class="rb-icon">${svg('bell')}</span> ${esc(rem.message)} <button class="sx" onclick="dismissReminder('${rem.id}')">Dismiss</button>`;
  document.getElementById('reminderBanners').appendChild(div);
}
function dismissReminder(id){
  const dismissed = JSON.parse(sessionStorage.getItem('dismissedReminders') || '[]');
  dismissed.push(id);
  sessionStorage.setItem('dismissedReminders', JSON.stringify(dismissed));
  document.querySelector(`[data-reminder="${id}"]`)?.remove();
}

/* ─── Upcoming reminders ───────────────────────────────────── */
async function refreshReminderCount(){
  const rems = await api('/api/reminders').catch(()=>[]);
  const badge = document.getElementById('remindersBadge');
  if (!badge) return rems;
  badge.textContent = rems.length;
  badge.hidden = !rems.length;
  return rems;
}
async function openReminders(){
  document.getElementById('remindersOverlay').classList.add('open');
  const list = document.getElementById('remindersList');
  list.innerHTML = '<div class="rem-empty">Loading…</div>';
  const rems = await refreshReminderCount();
  if (!rems.length){ list.innerHTML = '<div class="rem-empty">No upcoming reminders.</div>'; return; }
  list.innerHTML = rems.map(r => `
    <div class="rem-row" data-rem="${r.id}">
      <div class="rem-text">
        <div class="rem-when">${fmtDate(r.fire_at)}</div>
        <div class="rem-msg">${esc(r.message)}</div>
      </div>
      <button class="sx rem-del" onclick="deleteReminder('${r.id}')" title="Cancel reminder">✕</button>
    </div>`).join('');
}
function closeReminders(){ document.getElementById('remindersOverlay').classList.remove('open'); }
async function deleteReminder(id){
  await api('/api/reminders/'+id, { method:'DELETE' }).catch(()=>{});
  document.querySelector(`.rem-row[data-rem="${id}"]`)?.remove();
  refreshReminderCount();
  if (!document.querySelector('.rem-row'))
    document.getElementById('remindersList').innerHTML = '<div class="rem-empty">No upcoming reminders.</div>';
}

/* ─── Composer ─────────────────────────────────────────────── */
let composerMode = 'note', composerFeed = 'private', editingNoteId = null;
let composerAttachments = [];
const PLACEHOLDERS = {
  note: "What's on your mind…\n\nWrite freely. #tags are pulled out automatically.",
  todo: "Title on the first line…\nThen one task per line ([x] marks done).\n\n#tags work here too.",
};

function openComposer(){
  editingNoteId = null;
  document.getElementById('composerText').value = '';
  composerFeed = activeFeed;
  setComposerFeed(composerFeed);
  setComposerMode('note');
  composerAttachments = [];
  renderComposerFiles();
  document.getElementById('composer').classList.add('open');
  updateComposerTags();
  setTimeout(()=>document.getElementById('composerText').focus(),50);
}

/* ─── Composer attachments ─────────────────────────────────── */
function addComposerFiles(fileList){
  for (const f of fileList) composerAttachments.push(f);
  renderComposerFiles();
}
function removeComposerFile(i){
  composerAttachments.splice(i, 1);
  renderComposerFiles();
}
function renderComposerFiles(){
  document.getElementById('composerFileList').innerHTML = composerAttachments.map((f,i)=>
    `<span class="attach-chip">${esc(f.name)}<button type="button" title="Remove" onclick="removeComposerFile(${i})">✕</button></span>`).join('');
}
async function uploadAttachment(noteId, file){
  // Multipart, so no JSON header — can't reuse api().
  const fd = new FormData();
  fd.append('note_id', noteId);
  fd.append('file', file, file.name || 'pasted-image.png');
  const res = await fetch('/api/attachments', { method:'POST', body: fd });
  const data = await res.json().catch(()=>({}));
  if (!res.ok) throw new Error(data.error || 'Upload failed');
  return data;
}
// Same flow as the iOS composer: save the note first, upload each file, then
// append the returned markdown links so the images render in the card.
async function attachComposerFiles(note){
  if (!composerAttachments.length) return;
  const links = [];
  for (const f of composerAttachments){
    try { links.push((await uploadAttachment(note.id, f)).markdown); }
    catch (e) { toast(esc(e.message)); }
  }
  composerAttachments = [];
  renderComposerFiles();
  if (links.length){
    const content = (note.content ? note.content + '\n\n' : '') + links.join('\n');
    await api('/api/notes/'+note.id, { method:'PATCH', body: JSON.stringify({ content }) });
  }
}

function editNote(id){
  closeAllMenus();
  const n = notes.find(x=>x.id===id);
  if (!n) return;
  editingNoteId = id;
  composerFeed = n.feed;
  setComposerFeed(composerFeed);
  setComposerMode(n.type === 'todo' ? 'todo' : 'note');

  let text;
  if (n.type === 'todo') {
    const lines = [n.content.split('\n')[0]];
    for (const t of n.todos) lines.push(`${t.checked ? '[x] ' : ''}${t.text}`);
    text = lines.join('\n');
  } else {
    text = n.content;
  }
  if (n.tags.length) {
    text = text.trimEnd() + '\n\n' + n.tags.map(t=>'#'+t.name.toLowerCase()).join(' ');
  }
  document.getElementById('composerText').value = text;
  composerAttachments = [];
  renderComposerFiles();
  document.getElementById('composer').classList.add('open');
  updateComposerTags();
  setTimeout(()=>document.getElementById('composerText').focus(),50);
}
function closeComposer(){ document.getElementById('composer').classList.remove('open'); }
function setComposerMode(m){
  composerMode = m;
  document.getElementById('tabNote').classList.toggle('active', m==='note');
  document.getElementById('tabTodo').classList.toggle('active', m==='todo');
  updateComposerTags();
}
function setComposerFeed(f){
  composerFeed = f;
  document.getElementById('cFeedPrivate').classList.toggle('active', f==='private');
  document.getElementById('cFeedShared').classList.toggle('active', f==='shared');
}

/* pull #hashtags out of text; return {tags:[...], clean:textWithoutTags} */
function extractTags(text){
  const found = [];
  const clean = text.replace(/(^|\s)#([\p{L}\p{N}_-]+)/gu, (m,pre,word)=>{
    const name = word.toUpperCase();
    if (!found.includes(name)) found.push(name);
    return pre;
  }).replace(/[ \t]{2,}/g,' ');
  return { tags:found, clean };
}

function updateComposerTags(){
  document.getElementById('composerText').placeholder = PLACEHOLDERS[composerMode];
  const { tags:found } = extractTags(document.getElementById('composerText').value);
  const row = document.getElementById('composerTags');
  if (!found.length){ row.innerHTML = `<span class="ct-label">Add #tags as you type</span>`; return; }
  row.innerHTML = `<span class="ct-label">Tags</span>` + found.map((t,i)=>{
    const existing = tags.find(x=>x.name===t);
    const color = existing ? existing.color : PALETTE[(tags.length+i) % PALETTE.length];
    return `<span class="ct-pill ${existing?'':'ct-new'}" style="--tag-color:${color}">${esc(t)}${existing?'':' · new'}</span>`;
  }).join('');
  renderTagSuggestions(found);
}

/* One-tap reuse of existing tags so you don't retype them (or fork a near-dup). */
function renderTagSuggestions(found){
  const el = document.getElementById('composerSuggest');
  if (!el) return;
  const used = new Set(found);
  const avail = tags.filter(t => t.count && !used.has(t.name))
    .sort((a,b) => String(b.last_used||'').localeCompare(String(a.last_used||'')))
    .slice(0, 12);
  el.innerHTML = avail.length
    ? `<span class="ct-label">Add existing</span>` + avail.map(t =>
        `<button type="button" class="ct-suggest" style="--tag-color:${t.color}" onclick="addComposerTag('${esc(t.name)}')">${esc(t.name)}</button>`).join('')
    : '';
}

function addComposerTag(name){
  const ta = document.getElementById('composerText');
  const { tags:cur } = extractTags(ta.value);
  if (cur.includes(name)) return;   // already on the note
  const sep = ta.value && !/\s$/.test(ta.value) ? ' ' : '';
  ta.value = ta.value + sep + '#' + name.toLowerCase() + ' ';
  updateComposerTags();
  ta.focus();
}

async function saveNote(){
  const raw = document.getElementById('composerText').value.trim();
  // No text but a queued file is still a note — an image-only capture.
  if (!raw && !composerAttachments.length){ closeComposer(); return; }
  const { tags:found, clean } = extractTags(raw);
  const body = { feed: composerFeed, tags: found };
  if (!editingNoteId) body.source = 'web';

  if (composerMode==='todo'){
    const lines = clean.split('\n').map(l=>l.trim()).filter(Boolean);
    body.type = 'todo';
    body.content = lines.shift() || 'Untitled list';
    body.todos = lines.map(l=>{
      const m = l.match(/^\[( |x|X)\]\s*(.*)$/);
      return m ? { text: m[2], checked: m[1].toLowerCase()==='x' }
               : { text: l, checked: false };
    });
  } else {
    body.type = 'note';
    body.content = clean.trim();
  }

  try {
    const note = editingNoteId
      ? await api('/api/notes/'+editingNoteId, { method:'PATCH', body: JSON.stringify(body) })
      : await api('/api/notes', { method:'POST', body: JSON.stringify(body) });
    await attachComposerFiles(note);
    if (document.getElementById('remindOn').checked && document.getElementById('remindAt').value){
      await api('/api/reminders', { method:'POST', body: JSON.stringify({
        message: body.content.split('\n')[0].slice(0,120),
        fire_at: document.getElementById('remindAt').value + ':00',
        notify_web: true, notify_sms: true, note_id: note.id,
      }) });
      refreshReminderCount();
    }
    document.getElementById('composerText').value = '';
    document.getElementById('remindOn').checked = false;
    document.getElementById('remindAt').hidden = true;
    document.getElementById('remindAt').value = '';
    const wasEditing = !!editingNoteId;
    editingNoteId = null;
    closeComposer();
    toast(`${svg(composerMode==='todo'?'check':'app',13)} ${wasEditing?'Updated':(composerMode==='todo'?'List saved':'Note saved')}`);
    loadTags(); loadNotes(); refreshSharedBadge();
  } catch (e) { toast(esc(e.message)); }
}

/* ─── Theme ────────────────────────────────────────────────── */
function setThemeIcon(){
  const dark = document.documentElement.getAttribute('data-theme')==='dark';
  document.getElementById('themeBtn').innerHTML = svg(dark?'sun':'moon',14);
}
function toggleTheme(){
  const html = document.documentElement;
  const next = html.getAttribute('data-theme')==='dark'?'light':'dark';
  html.setAttribute('data-theme', next);
  localStorage.setItem('remndrs-theme', next);
  setThemeIcon();
}

async function logout(){
  await api('/api/auth/logout', { method:'POST' }).catch(()=>{});
  window.location = '/login';
}

/* ─── SSE ──────────────────────────────────────────────────── */
function startStream(){
  const evtSource = new EventSource('/api/stream');
  evtSource.onmessage = (e) => {
    const event = JSON.parse(e.data);
    if (event.type === 'heartbeat') return;
    if (event.type === 'reminder') { showReminderBanner(event.data); refreshReminderCount(); return; }
    loadTags(); loadNotes(); refreshSharedBadge();
  };
}

/* ─── Keyboard ─────────────────────────────────────────────── */
document.addEventListener('keydown', e=>{
  if (e.key==='Escape'){ closeSheet(); closeShare(); closeComposer(); closeTagAdd(); closeTagEdit(); closeSettings(); closeAllMenus(); }
  if ((e.metaKey||e.ctrlKey) && e.key==='Enter' && document.getElementById('composer').classList.contains('open')){ e.preventDefault(); saveNote(); }
  if (['INPUT','TEXTAREA','SELECT'].includes(document.activeElement.tagName)) return;
  if (e.key==='n' || e.key==='N'){ e.preventDefault(); openComposer(); }
  if (e.key==='/'){ e.preventDefault(); document.getElementById('search').focus(); }
});

/* ─── Init ─────────────────────────────────────────────────── */
const savedTheme = localStorage.getItem('remndrs-theme');
if (savedTheme) document.documentElement.setAttribute('data-theme', savedTheme);
document.querySelector('.composer-attach-btn').innerHTML = `${svg('clip',12)} Attach`;
// Pasting an image into the composer (e.g. a screenshot) queues it as a file.
document.getElementById('composerText').addEventListener('paste', (e) => {
  const files = [...(e.clipboardData?.files || [])];
  if (files.length){ e.preventDefault(); addComposerFiles(files); }
});
renderChanRail();
setThemeIcon();
loadChannelStatus();
loadTags();
loadNotes();
loadPeople();
refreshSharedBadge();
startStream();
api('/api/reminders/pending').then(rems => (rems||[]).forEach(showReminderBanner)).catch(()=>{});
refreshReminderCount();
