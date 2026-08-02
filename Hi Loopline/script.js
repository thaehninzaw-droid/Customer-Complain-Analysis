// ==========================================================================
// Pulse chart — currently drawn from mock data below. To connect a real
// backend: replace the body of fetchPulseData() with a fetch() call to
// your API (e.g. GET /api/issues/pulse returning an array of 0-100 values),
// and this will render exactly the same way. Nothing else needs to change.
// ==========================================================================
async function fetchPulseData() {
  // TODO(backend): replace with something like:
  // const res = await fetch(`${API_BASE}/issues/pulse`);
  // return await res.json(); // expects an array of numbers, 0-100
  return [25, 27, 55, 18, 78, 45, 88, 50, 95, 58, 70, 62];
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
    showToast("Message sent — we'll be in touch soon.");
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
    showToast("Thanks — your response has been recorded.");
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

function botReplyFor(userText) {
  const t = userText.toLowerCase();
  if (t.includes('refund') || t.includes('billing') || t.includes('charge')) {
    return "Got it — I've tagged this as a Billing issue. A support specialist typically follows up on these within a day.";
  }
  if (t.includes('login') || t.includes('password') || t.includes('account')) {
    return "That sounds like an Account issue. I've logged it under Account & Login for the team to review.";
  }
  if (t.includes('late') || t.includes('delivery') || t.includes('shipping')) {
    return "Thanks for flagging that — logged under Delivery. These tend to get picked up quickly once tagged.";
  }
  if (t.includes('thank')) {
    return "Happy to help! Feel free to submit the full survey above if you'd like it reviewed formally.";
  }
  return "Thanks for sharing that — I've logged it as a general issue for review. Anything else you'd like to add?";
}

function handleSend() {
  const value = chatText.value.trim();
  if (!value) return;
  addMessage(value, 'user');
  chatText.value = '';
  setTimeout(() => addMessage(botReplyFor(value), 'bot'), 500);
}

if (chatSend) chatSend.addEventListener('click', handleSend);
if (chatText) {
  chatText.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') handleSend();
  });
}

// ---------- Password show/hide toggle ----------
document.querySelectorAll('.pw-toggle').forEach((btn) => {
  btn.addEventListener('click', () => {
    const input = document.getElementById(btn.dataset.target);
    if (!input) return;
    const showing = input.type === 'text';
    input.type = showing ? 'password' : 'text';
    btn.querySelector('.icon-eye').style.display = showing ? 'block' : 'none';
    btn.querySelector('.icon-eye-off').style.display = showing ? 'none' : 'block';
    btn.setAttribute('aria-label', showing ? 'Show password' : 'Hide password');
  });
});
