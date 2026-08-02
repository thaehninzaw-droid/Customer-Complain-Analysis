// ==========================================================================
// Loopline — shared admin page logic
// Auth guard + API helpers used by admin-dashboard.html and
// admin-chatbot.html. Requires config.js (API_BASE) loaded first.
//
// Client-side role checking here is a UX convenience (redirect a non-admin
// away before they see a confusing empty dashboard) - it is NOT the real
// security boundary. Every /admin/* backend endpoint independently checks
// the session token belongs to an admin account (see
// backend/app/main.py's get_current_admin_id) - so even a tampered-with
// or bypassed frontend can't reach admin data without a real admin login.
// ==========================================================================

function adminGetSession() {
  try {
    const raw = sessionStorage.getItem('loopline_session');
    return raw ? JSON.parse(raw) : null;
  } catch (e) {
    return null;
  }
}

function adminAuthHeaders() {
  const session = adminGetSession();
  return session && session.token ? { Authorization: `Bearer ${session.token}` } : {};
}

function adminShowToast(message) {
  const toast = document.getElementById('toast');
  if (!toast) return;
  toast.textContent = message;
  toast.classList.add('show');
  clearTimeout(adminShowToast._t);
  adminShowToast._t = setTimeout(() => toast.classList.remove('show'), 2800);
}

/** Fetch wrapper that adds the admin auth header and handles 401/403
 * by bouncing back to admin-login.html - shared by every admin page's
 * data-fetching code so that logic lives in exactly one place. */
async function adminFetch(path, options = {}) {
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: { 'Content-Type': 'application/json', ...adminAuthHeaders(), ...(options.headers || {}) }
  });
  if (res.status === 401 || res.status === 403) {
    sessionStorage.removeItem('loopline_session');
    window.location.href = 'admin-login.html';
    throw new Error('Not authorized - redirecting to admin login.');
  }
  let data = null;
  try { data = await res.json(); } catch (e) { /* no body */ }
  if (!res.ok) {
    throw new Error((data && data.detail) || `Request failed (${res.status})`);
  }
  return data;
}

function adminGuardAndWireNav() {
  const session = adminGetSession();
  if (!session || session.user.role !== 'admin') {
    window.location.href = 'admin-login.html';
    return null;
  }
  const nameEl = document.getElementById('admin-name');
  if (nameEl) nameEl.textContent = session.user.username;
  const logoutBtn = document.getElementById('admin-logout');
  if (logoutBtn) {
    logoutBtn.addEventListener('click', () => {
      sessionStorage.removeItem('loopline_session');
      window.location.href = 'admin-login.html';
    });
  }
  return session;
}
