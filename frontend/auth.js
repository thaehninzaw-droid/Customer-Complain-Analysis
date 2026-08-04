// ==========================================================================
// Loopline — auth
// Talks to the real backend now (see ../backend/app/main.py: POST
// /auth/signup, POST /auth/login). The backend returns a session token -
// see DECISIONS.md #9 for why a bare user_id is never trusted from the
// client. Session (token + user object) lives in sessionStorage, not
// localStorage - it should clear when the tab closes, not persist forever
// (see docs/FRONTEND_INTEGRATION.md for the full reasoning).
// Requires config.js (defines API_BASE) loaded first.
// ==========================================================================

const LL_SESSION_KEY = 'loopline_session'; // { token, user: {user_id, username, email, joined, role} }

function llGetSession() {
  try {
    const raw = sessionStorage.getItem(LL_SESSION_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch (e) {
    return null;
  }
}
function llSetSession(authResponse) {
  sessionStorage.setItem(LL_SESSION_KEY, JSON.stringify(authResponse));
}
function llClearSession() {
  sessionStorage.removeItem(LL_SESSION_KEY);
}
function llFindCurrentUser() {
  const session = llGetSession();
  return session ? session.user : null;
}
function llAuthHeaders() {
  const session = llGetSession();
  if (!session || !session.token) return {};
  return { Authorization: `Bearer ${session.token}` };
}
function llFormatMonthYear(isoDate) {
  const d = new Date(isoDate);
  const months = ['January','February','March','April','May','June','July','August','September','October','November','December'];
  return `${months[d.getMonth()]} ${d.getFullYear()}`;
}

// ---------- validation rules (mirrors app/auth.py server-side - client
// validation is just for instant feedback; the server is the real gate) ----------
const RULES = {
  username: /^[A-Za-z][A-Za-z0-9 ]{2,19}$/,
  email: /^[^\s@]+@[^\s@]+\.[^\s@]+$/,
  hasLength: (pw) => pw.length >= 8,
  hasUpper: (pw) => /[A-Z]/.test(pw),
  hasSpecial: (pw) => /[!@#$%^&*]/.test(pw)
};

function showFieldError(fieldEl, message) {
  const field = fieldEl.closest('.field');
  field.classList.add('invalid');
  let err = field.querySelector('.field-error');
  if (!err) {
    err = document.createElement('div');
    err.className = 'field-error';
    field.appendChild(err);
  }
  err.textContent = message;
  err.classList.add('show');
}
function clearFieldError(fieldEl) {
  const field = fieldEl.closest('.field');
  field.classList.remove('invalid');
  const err = field.querySelector('.field-error');
  if (err) err.classList.remove('show');
}

async function llApiPost(path, body) {
  const res = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  });
  let data = null;
  try { data = await res.json(); } catch (e) { /* no body */ }
  if (!res.ok) {
    const message = (data && data.detail) ? data.detail : `Request failed (${res.status})`;
    throw new Error(message);
  }
  return data;
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

// ---------- signup ----------
const signupForm = document.getElementById('signup-form');
if (signupForm) {
  const nameInput = document.getElementById('su-name');
  const emailInput = document.getElementById('su-email');
  const passwordInput = document.getElementById('su-password');
  const confirmInput = document.getElementById('su-confirm');
  const checklist = document.getElementById('pw-checklist');

  function updateChecklist() {
    if (!checklist) return;
    const pw = passwordInput.value;
    checklist.querySelector('[data-rule="length"]').classList.toggle('ok', RULES.hasLength(pw));
    checklist.querySelector('[data-rule="upper"]').classList.toggle('ok', RULES.hasUpper(pw));
    checklist.querySelector('[data-rule="special"]').classList.toggle('ok', RULES.hasSpecial(pw));
  }
  if (passwordInput) passwordInput.addEventListener('input', updateChecklist);

  signupForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    let valid = true;

    const username = nameInput.value.trim();
    const email = emailInput.value.trim();
    const password = passwordInput.value;
    const confirm = confirmInput.value;

    [nameInput, emailInput, passwordInput, confirmInput].forEach(clearFieldError);

    if (!RULES.username.test(username)) {
      showFieldError(nameInput, 'Name must start with a letter and be 3–20 characters (letters, numbers, spaces).');
      valid = false;
    }
    if (!RULES.email.test(email)) {
      showFieldError(emailInput, 'Enter a valid email, e.g. you@example.com.');
      valid = false;
    }
    if (!(RULES.hasLength(password) && RULES.hasUpper(password) && RULES.hasSpecial(password))) {
      showFieldError(passwordInput, 'Password needs 8+ characters, one uppercase letter, and one special character (!@#$%^&*).');
      valid = false;
    }
    if (password !== confirm) {
      showFieldError(confirmInput, 'Passwords do not match.');
      valid = false;
    }
    if (!valid) return;

    const submitBtn = signupForm.querySelector('button[type="submit"]');
    if (submitBtn) submitBtn.disabled = true;

    try {
      const auth = await llApiPost('/auth/signup', { username, email, password });
      llSetSession(auth);
      showToast(`Account created — welcome, ${auth.user.username}!`);
      setTimeout(() => { window.location.href = 'activities.html'; }, 700);
    } catch (err) {
      if (/email/i.test(err.message)) {
        showFieldError(emailInput, err.message);
      } else {
        showToast(err.message || 'Could not create your account. Please try again.');
      }
    } finally {
      if (submitBtn) submitBtn.disabled = false;
    }
  });
}

// ---------- login ----------
const loginFormEl = document.getElementById('login-form');
if (loginFormEl) {
  const emailInput = document.getElementById('l-email');
  const passwordInput = document.getElementById('l-password');

  loginFormEl.addEventListener('submit', async (e) => {
    e.preventDefault();
    clearFieldError(emailInput);
    clearFieldError(passwordInput);

    const email = emailInput.value.trim();
    const password = passwordInput.value;

    const submitBtn = loginFormEl.querySelector('button[type="submit"]');
    if (submitBtn) submitBtn.disabled = true;

    try {
      const auth = await llApiPost('/auth/login', { email, password });
      llSetSession(auth);
      if (auth.user.role === 'admin') {
        showToast(`Welcome back, ${auth.user.username} — this is an admin account, redirecting to the Admin Dashboard.`);
        setTimeout(() => { window.location.href = 'admin-dashboard.html'; }, 900);
      } else {
        showToast(`Welcome back, ${auth.user.username}!`);
        setTimeout(() => { window.location.href = 'activities.html'; }, 700);
      }
    } catch (err) {
      showFieldError(passwordInput, err.message || 'Invalid email or password. Please try again.');
    } finally {
      if (submitBtn) submitBtn.disabled = false;
    }
  });
}

// ---------- guest (skips login, no session) ----------
// handled in script.js (guest-btn) — intentionally does NOT set a session,
// so the survey stays gated for guests.

// ---------- nav account state + gate activities page + survey gate ----------
document.addEventListener('DOMContentLoaded', () => {
  const session = llGetSession();

  // --- Gate: activities page is only for logged in users ---
  const onActivitiesPage = !!document.getElementById('complaint-table');
  if (onActivitiesPage && !session) {
    if (typeof showToast === 'function') showToast('Please log in to view Activities.');
    window.location.href = 'login.html';
    return;
  }

  // --- Nav auth: show Hi, [Name] + Logout when logged in ---
  const navAuth = document.querySelector('.nav-auth');
  if (navAuth && session) {
    const dashboardLink = session.user.role === 'admin'
      ? `<a href="admin-dashboard.html" class="btn btn-ghost btn-sm">Admin Dashboard</a>`
      : '';
    navAuth.innerHTML = `
      <div class="nav-account">
        <span>Hi, ${session.user.username}</span>
        ${dashboardLink}
        <button class="btn btn-ghost btn-sm" id="logout-btn">Log out</button>
      </div>`;
    const logoutBtn = document.getElementById('logout-btn');
    if (logoutBtn) logoutBtn.addEventListener('click', () => {
      llClearSession();
      window.location.href = 'index.html';
    });
  }

  // --- Activities profile card: show real user info (email, joined, name) ---
  const profileNameEl = document.querySelector('.profile-name');
  const profileEmailEl = document.getElementById('profile-email');
  const profileJoinedEl = document.getElementById('profile-joined');
  if (onActivitiesPage && session) {
    const user = session.user;
    if (profileNameEl) profileNameEl.textContent = user.username;
    if (profileEmailEl) profileEmailEl.textContent = user.email;
    if (profileJoinedEl) profileJoinedEl.textContent = llFormatMonthYear(user.joined);
  }

  // --- Survey gate on index.html ---
  const surveyGate = document.getElementById('survey-gate');
  const surveyForm = document.getElementById('survey-form');
  if (surveyGate && surveyForm) {
    if (session) {
      surveyGate.style.display = 'none';
      surveyForm.style.display = 'block';
    } else {
      surveyGate.style.display = 'block';
      surveyForm.style.display = 'none';
    }
  }
});
