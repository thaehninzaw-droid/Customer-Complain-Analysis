// ==========================================================================
// Pulse chart — real data from GET /issues/pulse (see ../backend/app/main.py).
// Falls back to a flat line if the API is unreachable, so the homepage
// never breaks just because the backend isn't running.
// ==========================================================================
async function fetchPulseData() {
  try {
    const res = await fetch(`${API_BASE}/issues/pulse`);
    if (!res.ok) throw new Error(`pulse fetch failed: ${res.status}`);
    return await res.json();
  } catch (e) {
    console.warn('Could not load live pulse data, showing a flat placeholder.', e);
    return new Array(12).fill(0);
  }
}

function renderPulseChart(data) {
  const bg = document.getElementById('pulse-bg');
  const line = document.getElementById('pulse-line');
  const dots = document.getElementById('pulse-dots');
  if (!bg || !line) return;

  const width = 320, height = 120, padding = 6;
  const step = width / (data.length - 1);
  const points = data.map((v, i) => {
    const x = i * step;
    const y = height - padding - (v / 100) * (height - padding * 2);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(' ');

  bg.setAttribute('points', points);
  line.setAttribute('points', points);

  // grow-in animation
  const length = line.getTotalLength ? line.getTotalLength() : 480;
  line.style.strokeDasharray = length;
  line.style.strokeDashoffset = length;
  line.getBoundingClientRect(); // force reflow
  line.style.transition = 'stroke-dashoffset 1.4s ease';
  line.style.strokeDashoffset = '0';

  // mark the highest point as a "spike" and the last two as "resolved"
  if (dots) {
    dots.innerHTML = '';
    const maxIndex = data.indexOf(Math.max(...data));
    data.forEach((v, i) => {
      if (i !== maxIndex && i < data.length - 2) return;
      const x = i * step, y = height - padding - (v / 100) * (height - padding * 2);
      const circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
      circle.setAttribute('cx', x);
      circle.setAttribute('cy', y);
      circle.setAttribute('r', 4.5);
      circle.setAttribute('fill', i === maxIndex ? '#FFC94A' : '#3F8489');
      dots.appendChild(circle);
    });
  }
}

if (document.getElementById('pulse-svg')) {
  fetchPulseData().then(renderPulseChart);
}

// ==========================================================================
// Categories — single source of truth is GET /categories (see
// ../backend/app/categories.py and ../docs/FRONTEND_INTEGRATION.md). Both
// the survey form (#s-category) and the complaint form (#f-category) used
// to hardcode their own copies of this list, and they'd already drifted
// apart from each other and from the backend. Fetching it once here means
// there's exactly one place this list is ever typed out again.
// ==========================================================================
async function populateCategorySelect(selectEl, { includeAutoDetect = false } = {}) {
  if (!selectEl) return;
  try {
    const res = await fetch(`${API_BASE}/categories`);
    if (!res.ok) throw new Error(`categories fetch failed: ${res.status}`);
    const categories = await res.json();
    const firstOption = includeAutoDetect
      ? '<option value="">Auto-detect for me</option>'
      : '<option value="">Choose a category</option>';
    selectEl.innerHTML = firstOption + categories.map(c => `<option value="${c}">${c}</option>`).join('');
  } catch (err) {
    console.warn('Could not load categories from the server, keeping the existing options.', err);
  }
}
populateCategorySelect(document.getElementById('s-category'));
// #f-category (activities.html) is populated in wireActivitiesPage() below,
// with includeAutoDetect:true, since it's optional there (Algorithm 1
// auto-classifies if left blank).

// ---------- Toast helper ----------
function showToast(message) {
  const toast = document.getElementById('toast');
  if (!toast) return;
  toast.textContent = message;
  toast.classList.add('show');
  clearTimeout(showToast._t);
  showToast._t = setTimeout(() => toast.classList.remove('show'), 2600);
}

// ---------- Nav mobile toggle ----------
const navToggle = document.querySelector('.nav-toggle');
const navLinks = document.querySelector('.nav-links');
if (navToggle && navLinks) {
  navToggle.addEventListener('click', () => {
    const isOpen = navLinks.style.display === 'flex';
    navLinks.style.display = isOpen ? 'none' : 'flex';
    navLinks.style.flexDirection = 'column';
    navLinks.style.position = 'absolute';
    navLinks.style.top = '64px';
    navLinks.style.left = '0';
    navLinks.style.right = '0';
    navLinks.style.background = '#EDF1F5';
    navLinks.style.padding = '18px 24px';
    navLinks.style.borderBottom = '1px solid #D7DEE5';
  });
}

// ---------- Contact form ----------
const contactForm = document.getElementById('contact-form');
if (contactForm) {
  contactForm.addEventListener('submit', (e) => {
    e.preventDefault();
    showToast("Message sent (demo) — we'll be in touch.");
    contactForm.reset();
  });
}

// ---------- Survey form + rating scale ----------
const ratingScale = document.getElementById('rating-scale');
let selectedRating = null;
if (ratingScale) {
  ratingScale.addEventListener('click', (e) => {
    const btn = e.target.closest('button');
    if (!btn) return;
    ratingScale.querySelectorAll('button').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    selectedRating = btn.dataset.value;
  });
}
const surveyForm = document.getElementById('survey-form');
if (surveyForm) {
  surveyForm.addEventListener('submit', (e) => {
    e.preventDefault();
    showToast("Thanks — your survey response was recorded (demo).");
    surveyForm.reset();
    ratingScale.querySelectorAll('button').forEach(b => b.classList.remove('active'));
    selectedRating = null;
  });
}

// ---------- Guest access (no session — survey stays gated) ----------
const guestBtn = document.getElementById('guest-btn');
if (guestBtn) {
  guestBtn.addEventListener('click', () => {
    showToast('Continuing as guest — sign in to unlock the survey.');
    setTimeout(() => { window.location.href = 'index.html'; }, 600);
  });
}

// ---------- AI chat widget ----------
const chatLauncher = document.getElementById('chat-launcher');
const chatPanel = document.getElementById('chat-panel');
const chatBody = document.getElementById('chat-body');
const chatText = document.getElementById('chat-text');
const chatSend = document.getElementById('chat-send');

if (chatLauncher && chatPanel) {
  chatLauncher.addEventListener('click', () => {
    chatPanel.classList.toggle('open');
    if (chatPanel.classList.contains('open')) chatText.focus();
  });
}

function addMessage(text, sender) {
  const msg = document.createElement('div');
  msg.className = `msg ${sender}`;
  msg.textContent = text;
  chatBody.appendChild(msg);
  chatBody.scrollTop = chatBody.scrollHeight;
}

async function getBotReply(userText) {
  try {
    const res = await fetch(`${API_BASE}/chatbot/recommend`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ complaint_text: userText })
    });
    if (!res.ok) throw new Error(`chatbot request failed: ${res.status}`);
    const data = await res.json();
    return `I've tagged this as a ${data.category} issue. ${data.recommendation}`;
  } catch (e) {
    console.warn('Chatbot request failed, showing a fallback reply.', e);
    return "Thanks for sharing that — I've logged it for review. (The AI assistant couldn't be reached just now, but a support specialist will still follow up.)";
  }
}

function handleSend() {
  const value = chatText.value.trim();
  if (!value) return;
  addMessage(value, 'user');
  chatText.value = '';

  const typingEl = document.createElement('div');
  typingEl.className = 'msg bot';
  typingEl.textContent = '…';
  chatBody.appendChild(typingEl);
  chatBody.scrollTop = chatBody.scrollHeight;

  getBotReply(value).then(reply => {
    typingEl.remove();
    addMessage(reply, 'bot');
  });
}

if (chatSend) chatSend.addEventListener('click', handleSend);
if (chatText) {
  chatText.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') handleSend();
  });
}

// ==========================================================================
// Activities Page — Complaint Management (Strict Validation)
//   - Per-user storage: each complaint stores user_id of owner
//   - NO pre-seeded data: new accounts start with empty complaint history
//   - Asia/Yangon (UTC+06:30) timezone for Myanmar date & time — no past allowed
//   - Complaint text: 20–1000 chars, ≥3 real words, rejects repeats/gibberish/test
//   - Profanity filter — case-insensitive bad-word check
//   - Searchable Myanmar city dropdown → auto-fill state + zip (both readonly)
// ==========================================================================
// Complaint data now comes from the real backend (see llRefreshComplaintsCache
// below) rather than localStorage.

// ---------------- Myanmar City Lookup ----------------
// One representative zip code per city (student-project friendly)
const MYANMAR_CITIES = [
  // Yangon Region
  { city: 'Yangon',           state: 'Yangon Region',            zip: '11181' },
  { city: 'Thanlyin',         state: 'Yangon Region',            zip: '11291' },
  { city: 'Insein',           state: 'Yangon Region',            zip: '11011' },
  { city: 'Hmawbi',          state: 'Yangon Region',            zip: '11141' },
  { city: 'Hlegu',           state: 'Yangon Region',            zip: '11171' },
  { city: 'Twante',          state: 'Yangon Region',            zip: '11241' },
  { city: 'Dala',            state: 'Yangon Region',            zip: '11231' },
  { city: 'Shwe Pyi Thar',   state: 'Yangon Region',            zip: '11411' },
  // Mandalay Region
  { city: 'Mandalay',        state: 'Mandalay Region',          zip: '05011' },
  { city: 'Pyin Oo Lwin',    state: 'Mandalay Region',          zip: '05081' },
  { city: 'Meiktila',        state: 'Mandalay Region',          zip: '05201' },
  { city: 'Kyaukse',         state: 'Mandalay Region',          zip: '05151' },
  { city: 'Myingyan',        state: 'Mandalay Region',          zip: '05121' },
  { city: 'Yamethin',        state: 'Mandalay Region',          zip: '05231' },
  { city: 'Myittha',         state: 'Mandalay Region',          zip: '05191' },
  // Naypyidaw UT
  { city: 'Naypyidaw',       state: 'Naypyidaw Union Territory',zip: '15011' },
  { city: 'Pyinmana',        state: 'Naypyidaw Union Territory',zip: '15021' },
  { city: 'Lewe',            state: 'Naypyidaw Union Territory',zip: '15031' },
  // Shan State
  { city: 'Taunggyi',        state: 'Shan State',               zip: '06011' },
  { city: 'Lashio',          state: 'Shan State',               zip: '06301' },
  { city: 'Muse',            state: 'Shan State',               zip: '06351' },
  { city: 'Kengtung',        state: 'Shan State',               zip: '06231' },
  { city: 'Kalaw',           state: 'Shan State',               zip: '06021' },
  { city: 'Nyaungshwe',      state: 'Shan State',               zip: '06031' },
  { city: 'Hsipaw',          state: 'Shan State',               zip: '06311' },
  // Sagaing Region
  { city: 'Sagaing',         state: 'Sagaing Region',           zip: '03011' },
  { city: 'Monywa',          state: 'Sagaing Region',           zip: '03111' },
  { city: 'Shwebo',          state: 'Sagaing Region',           zip: '03021' },
  { city: 'Kale',            state: 'Sagaing Region',           zip: '02011' },
  { city: 'Tamu',            state: 'Sagaing Region',           zip: '02031' },
  { city: 'Katha',           state: 'Sagaing Region',           zip: '03061' },
  // Ayeyarwady Region
  { city: 'Pathein',         state: 'Ayeyarwady Region',        zip: '10011' },
  { city: 'Hinthada',        state: 'Ayeyarwady Region',        zip: '10021' },
  { city: 'Pyapon',          state: 'Ayeyarwady Region',        zip: '10041' },
  { city: 'Bogale',          state: 'Ayeyarwady Region',        zip: '10061' },
  { city: 'Maubin',          state: 'Ayeyarwady Region',        zip: '10031' },
  { city: 'Chaungtha',       state: 'Ayeyarwady Region',        zip: '10071' },
  // Bago Region
  { city: 'Bago',            state: 'Bago Region',              zip: '08011' },
  { city: 'Taungoo',         state: 'Bago Region',              zip: '08111' },
  { city: 'Pyay',            state: 'Bago Region',              zip: '08151' },
  { city: 'Nyaunglebin',     state: 'Bago Region',              zip: '08061' },
  { city: 'Letpadan',        state: 'Bago Region',              zip: '08181' },
  // Magway Region
  { city: 'Magway',          state: 'Magway Region',            zip: '04011' },
  { city: 'Pakokku',         state: 'Magway Region',            zip: '04031' },
  { city: 'Minbu',           state: 'Magway Region',            zip: '04021' },
  { city: 'Thayet',          state: 'Magway Region',            zip: '04111' },
  // Tanintharyi Region
  { city: 'Dawei',           state: 'Tanintharyi Region',       zip: '14011' },
  { city: 'Myeik',           state: 'Tanintharyi Region',       zip: '14031' },
  { city: 'Kawthaung',       state: 'Tanintharyi Region',       zip: '14051' },
  // Mon State
  { city: 'Mawlamyine',      state: 'Mon State',                zip: '12011' },
  { city: 'Thaton',          state: 'Mon State',                zip: '12031' },
  { city: 'Kyaikto',         state: 'Mon State',                zip: '12061' },
  // Kayin State
  { city: 'Hpa-An',          state: 'Kayin State',              zip: '13011' },
  { city: 'Myawaddy',        state: 'Kayin State',              zip: '13031' },
  // Kayah State
  { city: 'Loikaw',          state: 'Kayah State',              zip: '09011' },
  // Chin State
  { city: 'Hakha',           state: 'Chin State',               zip: '07011' },
  { city: 'Falam',           state: 'Chin State',               zip: '07031' },
  // Kachin State
  { city: 'Myitkyina',       state: 'Kachin State',             zip: '01011' },
  { city: 'Bhamo',           state: 'Kachin State',             zip: '01031' },
  { city: 'Putao',           state: 'Kachin State',             zip: '01051' },
  // Rakhine State
  { city: 'Sittwe',          state: 'Rakhine State',            zip: '07011' },
  { city: 'Thandwe',         state: 'Rakhine State',            zip: '07111' },
  { city: 'Kyaukphyu',       state: 'Rakhine State',            zip: '07131' },
];

// ---------------- Profanity Filter ----------------
const PROFANE_WORDS = [
  'shit','fuck','damn','asshole','bitch','bastard','cunt','dick','piss','prick',
  'slut','whore','motherfucker','bullshit','horseshit','douche','douchebag',
  'wanker','arsehole','fucking','fucker','shitty','bollocks','twat','retard',
  'idiot','stupid','moron','dumbass','jerk','ass','nigger','nigga','chink',
  'spic','kike','fag','faggot','dyke','tranny','pussy','cock','crap','bloody',
  'hell','pissed','screw','screwed','bugger','sod','git','tosser','bellend',
  'muppet','plonker','wazzock','numpty','pillock','knob','knobhead','dickhead',
  'arse','arsewipe','shithead','fuckwit','fucktard','motherfucking','goddamn',
  'dammit','godammit','jesus','mary','for fuck sake','for fucks sake','f sake'
];
const PROFANE_RE = new RegExp('\\b(' + PROFANE_WORDS.map(w => w.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')).join('|') + ')\\b', 'i');

function containsProfanity(text) {
  if (!text) return false;
  if (PROFANE_RE.test(text)) return true;
  const words = text.toLowerCase().split(/[^a-z0-9]+/).filter(Boolean);
  for (const w of words) {
    for (const bad of PROFANE_WORDS) {
      if (w === bad) return true;
      if (w.length === bad.length && w.split('').sort().join('') === bad.split('').sort().join('')) {
        if (w === bad) return true;
      }
    }
  }
  return false;
}

// ---------------- Complaint Text Validation ----------------
const BANNED_SINGLE_WORDS = new Set(['hii','heyy','asdfgh','qwerty','zxcvbn','12345','123456','abc','asdf','qwer','poiu','lkjh','mnbv']);

function isMeaningfulComplaint(text) {
  if (!text) return false;
  const t = text.trim();
  if (t.length < 20) return { ok: false, reason: 'Please enter a meaningful description of your complaint.' };
  if (t.length > 1000) return { ok: false, reason: 'Please enter a meaningful description of your complaint.' };

  if (containsProfanity(t)) {
    return { ok: false, reason: 'Please avoid offensive or inappropriate language.' };
  }

  const onlyLetters = t.toLowerCase().split(/[^a-z]+/).filter(w => w.length > 0);
  let realWords = [];
  for (const w of onlyLetters) {
    if (w.length >= 2 && !/^([a-z])\1+$/.test(w) && !BANNED_SINGLE_WORDS.has(w)) {
      realWords.push(w);
    }
  }
  if (realWords.length < 3) {
    return { ok: false, reason: 'Please enter a meaningful description of your complaint.' };
  }

  const tLower = t.toLowerCase();
  if (/^([a-z])\1*$/.test(tLower.replace(/[^a-z]/g,''))) {
    return { ok: false, reason: 'Please enter a meaningful description of your complaint.' };
  }
  if (/^([0-9])\1*$/.test(tLower.replace(/[^0-9]/g,'')) && t.replace(/[^0-9]/g,'').length > 5) {
    return { ok: false, reason: 'Please enter a meaningful description of your complaint.' };
  }
  if (/^([^a-z0-9])\1*$/.test(tLower.replace(/[a-z0-9]/g,'')) && t.replace(/[a-z0-9]/g,'').length > 4) {
    return { ok: false, reason: 'Please enter a meaningful description of your complaint.' };
  }

  for (const bw of BANNED_SINGLE_WORDS) {
    if (tLower.split(/[^a-z0-9]+/).filter(Boolean).every(w => w === bw)) {
      return { ok: false, reason: 'Please enter a meaningful description of your complaint.' };
    }
  }

  return { ok: true };
}

// ---------------- Yangon Timezone Helpers (Asia/Yangon = UTC+06:30) ----------------
const YANGON_OFFSET_MIN = 6 * 60 + 30; // +06:30

function getYangonDateParts(jsDate) {
  const utcMs = jsDate.getTime() + jsDate.getTimezoneOffset() * 60000;
  const ygMs = utcMs + YANGON_OFFSET_MIN * 60000;
  const y = new Date(ygMs);
  return {
    y: y.getUTCFullYear(),
    m: y.getUTCMonth(),
    d: y.getUTCDate(),
    hh: y.getUTCHours(),
    mm: y.getUTCMinutes(),
    ss: y.getUTCSeconds(),
    ms: y.getUTCMilliseconds()
  };
}
function formatYangonDate(parts) {
  return `${parts.y}-${pad2(parts.m + 1)}-${pad2(parts.d)}`;
}
function makeDateObj(iso, h24, mm, ss) {
  const [y, m, d] = iso.split('-').map(n => parseInt(n, 10));
  const dt = new Date(Date.UTC(y, m - 1, d, h24, mm, ss));
  const utcMs = dt.getTime() - YANGON_OFFSET_MIN * 60000;
  return new Date(utcMs);
}

// ---------------- Shared helpers ----------------
// Complaints now live on the server (see ../backend/app/main.py:
// POST/GET /complaints) - user_id filtering happens server-side via the
// session token, never trusted from the client (see DECISIONS.md #9).
// This in-memory cache exists so all the synchronous rendering functions
// below (renderComplaintTable, updateComplaintStats, findComplaintByTicket)
// don't each need to become async - refresh the cache once after any
// change, then read from it everywhere else exactly like before.
let llComplaintsCache = [];

async function llRefreshComplaintsCache() {
  const session = typeof llGetSession === 'function' ? llGetSession() : null;
  if (!session) { llComplaintsCache = []; return llComplaintsCache; }
  try {
    const res = await fetch(`${API_BASE}/complaints`, { headers: llAuthHeaders() });
    if (!res.ok) throw new Error(`complaints fetch failed: ${res.status}`);
    llComplaintsCache = await res.json();
  } catch (e) {
    console.warn('Could not load complaints from the server.', e);
    if (typeof showToast === 'function') showToast('Could not load your complaints — check your connection.');
    llComplaintsCache = [];
  }
  return llComplaintsCache;
}

function llGetCurrentUserComplaints() {
  // Already filtered to "my complaints" server-side - see GET /complaints.
  return llComplaintsCache;
}

function formatDateDisplay(isoDate) {
  if (!isoDate) return '';
  const parts = isoDate.split('-');
  if (parts.length !== 3) return isoDate;
  return `${parts[2]}/${parts[1]}/${parts[0]}`;
}
function formatTimeDisplay(dbTime) {
  if (dbTime && dbTime.includes(':')) {
    const parts = dbTime.split(':');
    let h = parseInt(parts[0], 10);
    const m = parts[1];
    const s = parts[2] || '00';
    const suffix = h >= 12 ? 'PM' : 'AM';
    h = h % 12;
    if (h === 0) h = 12;
    return `${h}:${m}:${s} ${suffix}`;
  }
  return dbTime || '';
}
function pad2(n) { return String(n).padStart(2, '0'); }

function buildTimeSelectOptions() {
  const hourSel = document.getElementById('f-hour');
  const minSel = document.getElementById('f-minute');
  if (!hourSel || !minSel) return;
  if (hourSel.options.length === 0) {
    for (let h = 1; h <= 12; h++) {
      const opt = document.createElement('option');
      opt.value = pad2(h);
      opt.textContent = pad2(h);
      hourSel.appendChild(opt);
    }
  }
  if (minSel.options.length === 0) {
    for (let m = 0; m < 60; m++) {
      const opt = document.createElement('option');
      opt.value = pad2(m);
      opt.textContent = pad2(m);
      minSel.appendChild(opt);
    }
  }
}
function updateTimePreview() {
  const preview = document.getElementById('time-preview');
  if (!preview) return;
  const hourSel = document.getElementById('f-hour');
  const minSel = document.getElementById('f-minute');
  const ampmSel = document.getElementById('f-ampm');
  if (!hourSel || !minSel || !ampmSel) return;
  const h = hourSel.value;
  const m = minSel.value;
  const a = ampmSel.value;
  if (!h || !m || !a) return;
  preview.textContent = `${parseInt(h, 10)}:${m} ${a}`;
}

function updateComplaintStats() {
  const list = llGetCurrentUserComplaints();
  const total = list.length;
  const pending = list.filter(c => !['Resolved', 'Closed'].includes(c.status)).length;
  const resolved = list.filter(c => ['Resolved', 'Closed'].includes(c.status)).length;
  const setText = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };
  setText('stat-total', total);
  setText('stat-pending', pending);
  setText('stat-resolved', resolved);
  setText('card-total', total);
  setText('card-pending', pending);
  setText('card-resolved', resolved);
}

function renderComplaintTable(filterText) {
  const tbody = document.getElementById('complaint-tbody');
  const empty = document.getElementById('table-empty');
  if (!tbody) return;
  const me = typeof llFindCurrentUser === 'function' ? llFindCurrentUser() : null;
  if (!me) return;
  const list = llGetCurrentUserComplaints();
  const sorted = [...list].sort((a, b) => Number(a.ticket_no) - Number(b.ticket_no));
  let rows = sorted;
  if (filterText) {
    const f = filterText.toLowerCase();
    rows = sorted.filter(c => (
      String(c.ticket_no || '').toLowerCase().includes(f) ||
      (c.category || '').toLowerCase().includes(f) ||
      (c.complaint || '').toLowerCase().includes(f) ||
      (c.status || '').toLowerCase().includes(f) ||
      (c.city || '').toLowerCase().includes(f) ||
      (c.state || '').toLowerCase().includes(f)
    ));
  }
  tbody.innerHTML = '';
  if (rows.length === 0) {
    if (empty) {
      empty.style.display = 'block';
      empty.textContent = filterText ? 'No complaints match your search.' : 'No complaints yet. Click + New Complaint to file your first one.';
    }
    return;
  }
  if (empty) empty.style.display = 'none';
  const catColorMap = {
    'Billing': 'var(--amber-tint)', 'Financial': '#E8E4F0', 'Technical': '#E0EFEA',
    'Service': '#FFE7E0', 'Others': '#F0ECDC'
  };
  const catTextMap = {
    'Billing': 'var(--amber-dark)', 'Financial': '#5B4B8A', 'Technical': 'var(--teal-dark)',
    'Service': '#A24C2E', 'Others': '#7A6A2A'
  };
  rows.forEach(c => {
    const tr = document.createElement('tr');
    tr.className = 'complaint-row';
    tr.style.cursor = 'pointer';
    tr.dataset.ticket = String(c.ticket_no);
    tr.title = 'Click to view details';
    const statusClass = ['Resolved', 'Closed'].includes(c.status) ? 'resolved' : 'pending';
    const catBg = catColorMap[c.category] || 'var(--teal-tint)';
    const catCol = catTextMap[c.category] || 'var(--teal-dark)';
    const catStyle = `display:inline-block;padding:4px 10px;border-radius:100px;font-family:var(--font-mono);font-size:0.72rem;background:${catBg};color:${catCol};`;
    const safeComplaint = (c.complaint || '').replace(/"/g, '&quot;');
    tr.innerHTML = `
      <td><span class="ticket-no">#${c.ticket_no}</span></td>
      <td><span style="${catStyle}">${c.category || ''}</span></td>
      <td><div class="complaint-text" title="${safeComplaint}">${c.complaint || ''}</div></td>
      <td style="white-space:nowrap;font-family:var(--font-mono);font-size:0.84rem;color:var(--ink-soft);">${formatDateDisplay(c.date_month_year)}</td>
      <td style="white-space:nowrap;font-family:var(--font-mono);font-size:0.84rem;color:var(--ink-soft);">${formatTimeDisplay(c.time)}</td>
      <td>${c.city || ''}</td>
      <td>${c.state || ''}</td>
      <td style="font-family:var(--font-mono);">${c.zipcode || ''}</td>
      <td><span class="status-badge ${statusClass}">${c.status || 'Pending'}</span></td>
      <td>
        <div class="row-actions" style="display:flex;gap:6px;">
          <button type="button" class="row-btn row-btn-view" data-action="view" data-ticket="${c.ticket_no}" title="View details">👁 View</button>
        </div>
      </td>
    `;
    tr.addEventListener('click', (e) => {
      if (e.target.closest('[data-action]')) return;
      openViewModal(Number(c.ticket_no));
    });
    tbody.appendChild(tr);
  });

  tbody.querySelectorAll('[data-action="view"]').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      openViewModal(Number(btn.dataset.ticket));
    });
  });
}

// ---------------- City Searchable Dropdown ----------------
let cityActiveIndex = -1;
function renderCityOptions(filter = '') {
  const listEl = document.getElementById('city-options');
  if (!listEl) return;
  const f = filter.trim().toLowerCase();
  const items = MYANMAR_CITIES.filter(entry =>
    !f || entry.city.toLowerCase().includes(f) || entry.state.toLowerCase().includes(f)
  );
  listEl.innerHTML = '';
  if (items.length === 0) {
    const e = document.createElement('div');
    e.className = 'city-empty';
    e.textContent = 'No matching Myanmar city found.';
    listEl.appendChild(e);
    cityActiveIndex = -1;
    return;
  }
  cityActiveIndex = -1;
  items.forEach((entry, i) => {
    const opt = document.createElement('div');
    opt.className = 'city-option' + (i === 0 ? ' is-active' : '');
    opt.setAttribute('role', 'option');
    opt.dataset.city = entry.city;
    opt.dataset.state = entry.state;
    opt.dataset.zip = entry.zip;
    opt.innerHTML = `<span class="city-option-name">${entry.city}</span><span class="city-option-state">${entry.state}</span>`;
    opt.addEventListener('mousedown', (e) => {
      e.preventDefault();
      selectCity(entry.city, entry.state, entry.zip);
    });
    opt.addEventListener('mouseenter', () => {
      listEl.querySelectorAll('.city-option').forEach(n => n.classList.remove('is-active'));
      opt.classList.add('is-active');
      cityActiveIndex = i;
    });
    listEl.appendChild(opt);
  });
  if (items.length > 0) cityActiveIndex = 0;
}
function openCityDropdown() {
  const listEl = document.getElementById('city-options');
  if (!listEl) return;
  const search = document.getElementById('city-search');
  renderCityOptions(search ? search.value : '');
  listEl.classList.add('open');
}
function closeCityDropdown() {
  const listEl = document.getElementById('city-options');
  if (listEl) listEl.classList.remove('open');
}
function selectCity(cityName, stateName, zipVal) {
  const search = document.getElementById('city-search');
  const fCity = document.getElementById('f-city');
  const fState = document.getElementById('f-state');
  const fZip = document.getElementById('f-zip');
  if (search) search.value = cityName;
  if (fCity) fCity.value = cityName;
  if (fState) fState.value = stateName;
  if (fZip) fZip.value = zipVal;
  clearFieldError('err-city');
  setFieldValid('city-search', true);
  closeCityDropdown();
}
function wireCityDropdown() {
  const combo = document.getElementById('city-combo');
  if (!combo) return;
  const search = document.getElementById('city-search');
  const caret = document.getElementById('city-caret');
  const listEl = document.getElementById('city-options');
  if (search) {
    search.addEventListener('focus', () => openCityDropdown());
    search.addEventListener('input', () => {
      openCityDropdown();
      const val = search.value.trim();
      const match = MYANMAR_CITIES.find(e => e.city.toLowerCase() === val.toLowerCase());
      const fCity = document.getElementById('f-city');
      if (match) {
        selectCity(match.city, match.state, match.zip);
      } else if (fCity) {
        if (val !== fCity.value) {
          fCity.value = '';
          document.getElementById('f-state').value = '';
          document.getElementById('f-zip').value = '';
        }
      }
    });
    search.addEventListener('keydown', (e) => {
      if (!listEl.classList.contains('open') && (e.key === 'ArrowDown' || e.key === 'Enter')) {
        openCityDropdown();
        return;
      }
      const opts = listEl.querySelectorAll('.city-option');
      if (opts.length === 0) return;
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        cityActiveIndex = (cityActiveIndex + 1) % opts.length;
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        cityActiveIndex = (cityActiveIndex - 1 + opts.length) % opts.length;
      } else if (e.key === 'Enter') {
        e.preventDefault();
        const pick = opts[cityActiveIndex];
        if (pick) selectCity(pick.dataset.city, pick.dataset.state, pick.dataset.zip);
        return;
      } else if (e.key === 'Escape') {
        closeCityDropdown();
        return;
      } else return;
      opts.forEach(n => n.classList.remove('is-active'));
      opts[cityActiveIndex].classList.add('is-active');
      opts[cityActiveIndex].scrollIntoView({ block: 'nearest' });
    });
    search.addEventListener('blur', () => setTimeout(() => closeCityDropdown(), 120));
  }
  if (caret) {
    caret.addEventListener('mousedown', (e) => {
      e.preventDefault();
      if (listEl.classList.contains('open')) closeCityDropdown();
      else { if (search) search.focus(); }
    });
  }
  document.addEventListener('click', (e) => {
    if (!combo.contains(e.target)) closeCityDropdown();
  });
}

// ---------------- Field error display helpers ----------------
function showFieldError(id, msg) {
  const el = document.getElementById(id);
  if (!el) return;
  el.textContent = msg;
  el.classList.add('is-visible');
  if (id === 'err-complaint') setFieldValid('f-complaint', false);
  if (id === 'err-date') setFieldValid('f-date', false);
  if (id === 'err-time') {
    ['f-hour','f-minute','f-ampm'].forEach(fid => setFieldValid(fid, false));
  }
  if (id === 'err-city') setFieldValid('city-search', false);
}
function clearFieldError(id) {
  const el = document.getElementById(id);
  if (!el) return;
  el.textContent = '';
  el.classList.remove('is-visible');
  if (id === 'err-complaint') setFieldValid('f-complaint', true);
  if (id === 'err-date') setFieldValid('f-date', true);
  if (id === 'err-time') {
    ['f-hour','f-minute','f-ampm'].forEach(fid => setFieldValid(fid, true));
  }
  if (id === 'err-city') setFieldValid('city-search', true);
}
function setFieldValid(id, valid) {
  const el = document.getElementById(id);
  if (!el) return;
  if (valid) el.removeAttribute('aria-invalid');
  else el.setAttribute('aria-invalid', 'true');
}

// ---------------- Complaint submission ----------------
function convertTimeToDb(hour12, minute, second, ampm) {
  let h = parseInt(hour12, 10);
  if (ampm === 'AM' && h === 12) h = 0;
  if (ampm === 'PM' && h !== 12) h += 12;
  return `${pad2(h)}:${pad2(parseInt(minute, 10))}:${pad2(parseInt(second, 10))}`;
}
function validateDateTimeYangon(iso, h12, mm, ss, ampm) {
  // Complaints describe events that already happened — past dates and
  // past times today are intentionally allowed. Only future dates are
  // rejected. The backend stamps the real submission timestamp server-side.
  if (!iso) return { ok: false, dateErr: 'Please pick a date.', timeErr: '' };
  const nowParts = getYangonDateParts(new Date());
  const [yPicked, mPicked, dPicked] = iso.split('-').map(n => parseInt(n, 10));
  if (yPicked > nowParts.y ||
      (yPicked === nowParts.y && (mPicked - 1) > nowParts.m) ||
      (yPicked === nowParts.y && (mPicked - 1) === nowParts.m && dPicked > nowParts.d)) {
    return { ok: false, dateErr: 'Date cannot be in the future.', timeErr: '' };
  }
  return { ok: true };
}

function openComplaintModal() {
  const modal = document.getElementById('complaint-modal');
  if (!modal) return;
  buildTimeSelectOptions();

  ['err-complaint','err-date','err-time','err-city'].forEach(clearFieldError);
  // Also explicitly reset aria-invalid on all inputs so the red border
  // from a previous failed submit doesn't bleed into the next modal open.
  ['f-complaint','f-date','f-hour','f-minute','f-ampm','city-search'].forEach(id => setFieldValid(id, true));

  const ticketInput = document.getElementById('f-ticket');
  if (ticketInput) ticketInput.value = 'Assigned automatically on submit';

  const cat = document.getElementById('f-category');
  if (cat) cat.value = '';
  const complaint = document.getElementById('f-complaint');
  if (complaint) complaint.value = '';
  const citySearch = document.getElementById('city-search');
  if (citySearch) citySearch.value = '';
  const fCity = document.getElementById('f-city');
  if (fCity) fCity.value = '';
  const fState = document.getElementById('f-state');
  if (fState) fState.value = '';
  const fZip = document.getElementById('f-zip');
  if (fZip) fZip.value = '';

  // Defaults = current YANGON date & time
  const now = new Date();
  const yg = getYangonDateParts(now);
  const dateInput = document.getElementById('f-date');
  if (dateInput) {
    dateInput.value = formatYangonDate(yg);
    dateInput.max = formatYangonDate(yg); // future dates not allowed
  }

  const hourSel = document.getElementById('f-hour');
  const minSel = document.getElementById('f-minute');
  const ampmSel = document.getElementById('f-ampm');
  let h12 = yg.hh % 12;
  if (h12 === 0) h12 = 12;
  const suffix = yg.hh >= 12 ? 'PM' : 'AM';
  if (hourSel) hourSel.value = pad2(h12);
  if (minSel) minSel.value = pad2(yg.mm);
  if (ampmSel) ampmSel.value = suffix;

  updateTimePreview();
  modal.classList.add('open');
  document.body.style.overflow = 'hidden';
  setTimeout(() => {
    const f = document.getElementById('f-category');
    if (f) f.focus();
  }, 150);
}
function closeComplaintModal() {
  const modal = document.getElementById('complaint-modal');
  if (!modal) return;
  modal.classList.remove('open');
  document.body.style.overflow = '';
  closeCityDropdown();
}

// ---------------- View Complaint Details Modal ----------------
function findComplaintByTicket(ticketNo) {
  return llComplaintsCache.find(c => Number(c.ticket_no) === Number(ticketNo)) || null;
}

function buildViewDetailsMarkup(c) {
  const catColorMap = {
    'Billing': 'var(--amber-tint)', 'Financial': '#E8E4F0', 'Technical': '#E0EFEA',
    'Service': '#FFE7E0', 'Others': '#F0ECDC'
  };
  const catTextMap = {
    'Billing': 'var(--amber-dark)', 'Financial': '#5B4B8A', 'Technical': 'var(--teal-dark)',
    'Service': '#A24C2E', 'Others': '#7A6A2A'
  };
  const catBg = catColorMap[c.category] || 'var(--teal-tint)';
  const catCol = catTextMap[c.category] || 'var(--teal-dark)';
  const statusClass = ['Resolved', 'Closed'].includes(c.status) ? 'resolved' : 'pending';
  return `
    <div class="view-grid">
      <div class="view-field">
        <span class="view-label">Ticket #</span>
        <span class="view-value ticket-no">#${c.ticket_no}</span>
      </div>
      <div class="view-field">
        <span class="view-label">Category</span>
        <span class="view-value" style="display:inline-block;padding:4px 10px;border-radius:100px;font-family:var(--font-mono);font-size:0.72rem;background:${catBg};color:${catCol};">${c.category || ''}</span>
      </div>
      <div class="view-field">
        <span class="view-label">Date</span>
        <span class="view-value" style="font-family:var(--font-mono);color:var(--ink-soft);">${formatDateDisplay(c.date_month_year)}</span>
      </div>
      <div class="view-field">
        <span class="view-label">Time</span>
        <span class="view-value" style="font-family:var(--font-mono);color:var(--ink-soft);">${formatTimeDisplay(c.time)}</span>
      </div>
      <div class="view-field">
        <span class="view-label">City</span>
        <span class="view-value">${c.city || ''}</span>
      </div>
      <div class="view-field">
        <span class="view-label">State / Region</span>
        <span class="view-value">${c.state || ''}</span>
      </div>
      <div class="view-field">
        <span class="view-label">Zip Code</span>
        <span class="view-value" style="font-family:var(--font-mono);">${c.zipcode || ''}</span>
      </div>
      <div class="view-field">
        <span class="view-label">Status</span>
        <span class="status-badge ${statusClass}">${c.status || 'Pending'}</span>
      </div>
    </div>
    <div class="view-field" style="margin-top:18px;">
      <span class="view-label">Complaint Description</span>
      <div class="view-complaint-block">${c.complaint || ''}</div>
    </div>
  `;
}

function openViewModal(ticketNo) {
  const c = findComplaintByTicket(ticketNo);
  const modal = document.getElementById('view-modal');
  const body = document.getElementById('view-body');
  if (!modal || !body) return;
  if (!c) { showToast('Complaint not found.'); return; }
  body.innerHTML = buildViewDetailsMarkup(c);
  modal.classList.add('open');
  document.body.style.overflow = 'hidden';
}

function closeViewModal() {
  const modal = document.getElementById('view-modal');
  if (!modal) return;
  modal.classList.remove('open');
  document.body.style.overflow = '';
}

// NOTE: there used to be an Edit Complaint modal here letting customers
// change a complaint's category/status directly. That's been removed -
// per the SRS, editing category/status is an Admin Dashboard capability
// (Module 3.1: "Edit complaint details", "Update complaint status"), not
// a Customer Portal one (customers only "view" status - see the SRS's
// Complaint History & Status Tracking section). The old localStorage-only
// demo allowed it purely because there was no server-side authorization
// yet to enforce the distinction. See docs/FRONTEND_INTEGRATION.md and
// DECISIONS.md for the full writeup. The admin-dashboard.html page is
// where this capability now lives, backed by
// PATCH /admin/complaints/{ticket_no}.

function wireActivitiesPage() {
  const newBtn = document.getElementById('btn-new-complaint');
  if (newBtn) newBtn.addEventListener('click', openComplaintModal);

  const closeX = document.getElementById('modal-close');
  if (closeX) closeX.addEventListener('click', closeComplaintModal);
  const cancelBtn = document.getElementById('btn-cancel');
  if (cancelBtn) cancelBtn.addEventListener('click', closeComplaintModal);
  const overlay = document.getElementById('complaint-modal');
  if (overlay) {
    overlay.addEventListener('click', (e) => {
      if (e.target === overlay) closeComplaintModal();
    });
  }

  ['f-hour','f-minute','f-ampm'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.addEventListener('change', () => {
      updateTimePreview();
      clearFieldError('err-time');
    });
  });

  const complaintInput = document.getElementById('f-complaint');
  if (complaintInput) {
    // On input: only clear the error once the text becomes valid.
    // Never show the error mid-sentence — that fires on every keystroke
    // and marks the field red before the user has finished typing.
    complaintInput.addEventListener('input', () => {
      const v = complaintInput.value;
      if (v.trim().length === 0) { clearFieldError('err-complaint'); return; }
      if (isMeaningfulComplaint(v).ok) clearFieldError('err-complaint');
      // Don't call showFieldError here — wait for blur.
    });
    // On blur: now it's safe to show the error if still invalid.
    complaintInput.addEventListener('blur', () => {
      const v = complaintInput.value;
      if (v.trim().length === 0) { clearFieldError('err-complaint'); return; }
      const res = isMeaningfulComplaint(v);
      if (res.ok) clearFieldError('err-complaint');
      else showFieldError('err-complaint', res.reason);
    });
  }
  const dateInput = document.getElementById('f-date');
  if (dateInput) {
    dateInput.addEventListener('change', () => clearFieldError('err-date'));
  }

  wireCityDropdown();

  const searchInput = document.getElementById('complaint-search');
  if (searchInput) {
    let searchTimer;
    searchInput.addEventListener('input', () => {
      clearTimeout(searchTimer);
      searchTimer = setTimeout(() => {
        renderComplaintTable(searchInput.value.trim());
      }, 120);
    });
  }

  const form = document.getElementById('complaint-form');
  if (form) {
    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      const me = typeof llFindCurrentUser === 'function' ? llFindCurrentUser() : null;
      if (!me) { showToast('Please log in to submit a complaint.'); return; }

      ['err-complaint','err-date','err-time','err-city'].forEach(clearFieldError);

      const category = document.getElementById('f-category').value || null;
      const complaint = document.getElementById('f-complaint').value.trim();
      const date_month_year = document.getElementById('f-date').value;
      const hour12 = document.getElementById('f-hour').value;
      const minute = document.getElementById('f-minute').value;
      const second = '00'; // seconds removed from UI; backend stamps real time
      const ampm = document.getElementById('f-ampm').value;
      const city = (document.getElementById('f-city').value || '').trim();
      const state = (document.getElementById('f-state').value || '').trim();
      const zipcode = (document.getElementById('f-zip').value || '').trim();

      let valid = true;

      const cRes = isMeaningfulComplaint(complaint);
      if (!cRes.ok) { showFieldError('err-complaint', cRes.reason); valid = false; }

      if (!date_month_year) { showFieldError('err-date', 'Please pick a date.'); valid = false; }
      const dtRes = validateDateTimeYangon(date_month_year, hour12, minute, second, ampm);
      if (!dtRes.ok) {
        if (dtRes.dateErr) showFieldError('err-date', dtRes.dateErr);
        if (dtRes.timeErr) showFieldError('err-time', dtRes.timeErr);
        valid = false;
      }

      if (!city) { showFieldError('err-city', 'Please choose a city from the list.'); valid = false; }
      else if (!MYANMAR_CITIES.some(e => e.city === city)) {
        showFieldError('err-city', 'Please choose a city from the list.'); valid = false;
      }

      if (!valid) return;

      // Note: date/time picked in the form aren't sent - the backend
      // stamps the complaint with the real server-side submission time
      // (see POST /complaints in app/main.py). The picker above is kept
      // for the meaningful "when did this happen" UX check, matching the
      // original design, but a filed complaint's official timestamp is
      // always "now," server-side.
      const submitBtn = form.querySelector('button[type="submit"]');
      if (submitBtn) submitBtn.disabled = true;

      try {
        const res = await fetch(`${API_BASE}/complaints`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', ...llAuthHeaders() },
          body: JSON.stringify({ complaint, city, state, zipcode, category })
        });
        let data = null;
        try { data = await res.json(); } catch (e2) { /* no body */ }
        if (!res.ok) {
          const message = (data && data.detail) ? data.detail : `Request failed (${res.status})`;
          throw new Error(message);
        }

        await llRefreshComplaintsCache();
        renderComplaintTable(searchInput ? searchInput.value.trim() : '');
        updateComplaintStats();
        closeComplaintModal();
        showToast(`Complaint #${data.ticket_no} filed successfully.`);
      } catch (err) {
        showToast(err.message || 'Could not submit your complaint. Please try again.');
      } finally {
        if (submitBtn) submitBtn.disabled = false;
      }
    });
  }

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      const cModal = document.getElementById('complaint-modal');
      if (cModal && cModal.classList.contains('open')) closeComplaintModal();
      const vModal = document.getElementById('view-modal');
      if (vModal && vModal.classList.contains('open')) closeViewModal();
    }
  });

  // View Modal wiring
  (function () {
    const closeX = document.getElementById('view-close');
    if (closeX) closeX.addEventListener('click', closeViewModal);
    const closeBtn = document.getElementById('view-close-btn');
    if (closeBtn) closeBtn.addEventListener('click', closeViewModal);
    const overlay = document.getElementById('view-modal');
    if (overlay) {
      overlay.addEventListener('click', (e) => {
        if (e.target === overlay) closeViewModal();
      });
    }
  })();

  buildTimeSelectOptions();
  populateCategorySelect(document.getElementById('f-category'), { includeAutoDetect: true });
  llRefreshComplaintsCache().then(() => {
    renderComplaintTable();
    updateComplaintStats();
  });
}

if (document.getElementById('complaint-table') || document.getElementById('complaint-form')) {
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', wireActivitiesPage);
  } else {
    wireActivitiesPage();
  }
}
