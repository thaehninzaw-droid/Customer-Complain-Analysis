// ==========================================================================
// Loopline — auth (demo only)
// Users and sessions are stored in localStorage so the flow works without
// a backend yet. Swap LL_API.* for real fetch() calls once a backend
// exists — see the LL_API section at the bottom for where to plug it in.
// ==========================================================================

const LL_USERS_KEY = 'loopline_users';
const LL_SESSION_KEY = 'loopline_currentUser';

function llGetUsers() {
  return JSON.parse(localStorage.getItem(LL_USERS_KEY)) || [];
}
function llSaveUsers(users) {
  localStorage.setItem(LL_USERS_KEY, JSON.stringify(users));
}
function llGetSession() {
  return localStorage.getItem(LL_SESSION_KEY);
}
function llSetSession(username) {
  localStorage.setItem(LL_SESSION_KEY, username);
}
function llClearSession() {
  localStorage.removeItem(LL_SESSION_KEY);
}

// ---------- validation rules ----------
const RULES = {
  username: /^[A-Za-z][A-Za-z0-9 ]{2,19}$/,          // starts with a letter, 3-20 chars total
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

  signupForm.addEventListener('submit', (e) => {
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

    const users = llGetUsers();
    if (users.some(u => u.email.toLowerCase() === email.toLowerCase())) {
      showFieldError(emailInput, 'An account with this email already exists.');
      return;
    }

  fetch("http://127.0.0.1:5000/signup", {
    method: "POST",
    headers: {
        "Content-Type": "application/json"
    },
    body: JSON.stringify({
        name: username,
        email: email,
        password: password
    })
})
.then(response => response.json())
.then(data => {
    alert(data.message);

    if (data.message === "Signup Successful") {
        window.location.href = "login.html";
    }
})
.catch(error => {
    console.error(error);
    alert("Something went wrong!");
});
  });
}

// ---------- login ----------
// ---------- login ----------
const loginFormEl = document.getElementById('login-form');

if (loginFormEl) {
    const emailInput = document.getElementById('l-email');
    const passwordInput = document.getElementById('l-password');

    loginFormEl.addEventListener('submit', (e) => {
        e.preventDefault();

        clearFieldError(emailInput);
        clearFieldError(passwordInput);

        const email = emailInput.value.trim();
        const password = passwordInput.value;

        fetch("http://127.0.0.1:5000/login", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                email: email,
                password: password
            })
        })
        .then(response => response.json())
        .then(data => {

            if (data.message === "Login Successful") {

                llSetSession(data.name);

                showToast(`Welcome back, ${data.name}!`);

                setTimeout(() => {
                    window.location.href = "index.html#survey";
                }, 700);

            } else {
                showFieldError(passwordInput, data.message);
            }

        })
        .catch(error => {
            console.error(error);
            alert("Something went wrong!");
        });

    });
}

// ---------- guest (skips login, no session) ----------
// handled in script.js (guest-btn) — intentionally does NOT set a session,
// so the survey stays gated for guests.

// ---------- nav account state + survey gate (index.html) ----------
document.addEventListener('DOMContentLoaded', () => {
  const session = llGetSession();
  const navAuth = document.querySelector('.nav-auth');

  if (navAuth && session) {
    navAuth.innerHTML = `
      <div class="nav-account">
        <span>Hi, ${session}</span>
        <button class="btn btn-ghost btn-sm" id="logout-btn">Log out</button>
      </div>`;
    document.getElementById('logout-btn').addEventListener('click', () => {
      llClearSession();
      window.location.href = 'index.html';
    });
  }

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

// ==========================================================================
// LL_API — where a real backend plugs in
// Once you send me the backend's base URL and endpoints, this is the file
// that changes: signup/login stop touching localStorage and instead do
// something like:
//
//   const res = await fetch(`${API_BASE}/auth/signup`, {
//     method: 'POST',
//     headers: { 'Content-Type': 'application/json' },
//     body: JSON.stringify({ username, email, password })
//   });
//
// The backend (Mongo-backed, per your note) would own validation +
// storage server-side; the front end would just read res.ok / res.json().
// Same idea for the pulse graph data in script.js's renderPulseChart —
// see fetchPulseData() there.
// ==========================================================================
