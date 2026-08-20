// ==========================================================================
// Loopline — admin-customers.js
// Customer account list + profile modal for the admin portal.
// Requires config.js (API_BASE) and admin.js (adminFetch,
// adminGuardAndWireNav) to be loaded first.
// ==========================================================================

'use strict';

// ─── State ────────────────────────────────────────────────────────────────────
let _page          = 1;
const PAGE_SIZE    = 20;
let _search        = '';
let _debounceTimer = null;
// Cache the full page response so stat cards can be computed client-side.
let _lastData      = null;

// ─── Utilities ────────────────────────────────────────────────────────────────
function escapeHtml(str) {
  const d = document.createElement('div');
  d.textContent = (str == null) ? '' : String(str);
  return d.innerHTML;
}

function statusClassFor(s) {
  return ['Resolved', 'Closed'].includes(s) ? 'resolved' : 'pending';
}

function priorityClassFor(p) {
  return (p || 'low').toLowerCase();
}

/** Format an ISO date string to YYYY-MM-DD, gracefully. */
function fmtDate(iso) {
  if (!iso) return '—';
  return String(iso).slice(0, 10);
}

// ─── Stat cards ───────────────────────────────────────────────────────────────
function updateStatCards(data) {
  const total = data.total;
  const open  = data.items.filter(u => u.complaint_count > 0).length;
  // "none" is approximate for the current page; for full accuracy we'd need
  // a separate API call. Good enough for a summary.
  const none  = data.items.filter(u => u.complaint_count === 0).length;

  document.getElementById('stat-total').textContent = total;
  // Show page-scoped numbers with a note when paginated
  const suffix = total > PAGE_SIZE ? '*' : '';
  document.getElementById('stat-open').textContent = open + suffix;
  document.getElementById('stat-none').textContent = none + suffix;
}

// ─── Customer list ────────────────────────────────────────────────────────────
async function loadCustomers() {
  const tbody   = document.getElementById('cust-tbody');
  const emptyEl = document.getElementById('cust-empty');
  const loadEl  = document.getElementById('cust-loading');
  const pagEl   = document.getElementById('cust-pagination');

  tbody.innerHTML   = '';
  emptyEl.style.display = 'none';
  loadEl.style.display  = 'block';
  pagEl.style.display   = 'none';

  const params = new URLSearchParams({ page: _page, page_size: PAGE_SIZE });
  if (_search.trim()) params.set('search', _search.trim());

  try {
    const data = await adminFetch(`/admin/customers?${params}`);
    _lastData = data;
    loadEl.style.display = 'none';

    updateStatCards(data);

    if (!data.items.length) {
      emptyEl.textContent   = _search ? 'No customers match your search.' : 'No customer accounts yet.';
      emptyEl.style.display = 'block';
      return;
    }

    data.items.forEach(u => {
      const tr = document.createElement('tr');
      const countClass = u.complaint_count === 0 ? 'zero' : '';
      tr.innerHTML = `
        <td style="font-family:var(--font-mono); color:var(--ink-faint); font-size:0.85rem;">#${u.user_id}</td>
        <td style="font-weight:600;">${escapeHtml(u.username)}</td>
        <td style="color:var(--ink-faint); font-size:0.875rem;">${escapeHtml(u.email)}</td>
        <td style="font-family:var(--font-mono); font-size:0.82rem; color:var(--ink-faint);">${fmtDate(u.joined)}</td>
        <td><span class="count-badge ${countClass}">${u.complaint_count}</span></td>
        <td>
          <button type="button" class="row-btn row-btn-view"
                  data-action="view-customer"
                  data-userid="${u.user_id}"
                  data-username="${escapeHtml(u.username)}">
            <svg viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg"
                 style="width:12px;height:12px;margin-right:4px;vertical-align:-1px;">
              <circle cx="8" cy="6" r="2.5" stroke="currentColor" stroke-width="1.5"/>
              <path d="M2 13c0-3.314 2.686-5 6-5s6 1.686 6 5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
            </svg>View
          </button>
        </td>
      `;
      tbody.appendChild(tr);
    });

    // Event delegation — single listener on tbody
    tbody.addEventListener('click', e => {
      const btn = e.target.closest('[data-action="view-customer"]');
      if (btn) openCustomerModal(Number(btn.dataset.userid), btn.dataset.username);
    }, { once: false });

    // Pagination
    const totalPages = Math.max(1, Math.ceil(data.total / data.page_size));
    document.getElementById('cust-page-info').textContent =
      `Page ${data.page} of ${totalPages}`;
    document.getElementById('cust-prev').disabled = data.page <= 1;
    document.getElementById('cust-next').disabled = data.page >= totalPages;
    pagEl.style.display = 'flex';

  } catch (err) {
    loadEl.style.display  = 'none';
    emptyEl.textContent   = err.message || 'Failed to load customers.';
    emptyEl.style.display = 'block';
  }
}

// ─── Customer detail modal ────────────────────────────────────────────────────
async function openCustomerModal(userId, username) {
  const modal    = document.getElementById('cust-modal');
  const titleEl  = document.getElementById('cust-modal-title');
  const bodyEl   = document.getElementById('cust-modal-body');

  titleEl.textContent = username;
  bodyEl.innerHTML    = '<p style="color:var(--ink-faint);padding:2rem 0;text-align:center;">Loading…</p>';
  modal.classList.add('open');
  document.body.style.overflow = 'hidden';

  try {
    const data = await adminFetch(`/admin/customers/${userId}`);
    renderCustomerModal(data);
  } catch (err) {
    bodyEl.innerHTML =
      `<p style="color:var(--danger);padding:1rem 0;">${escapeHtml(err.message || 'Could not load profile.')}</p>`;
  }
}

function renderCustomerModal(data) {
  const u          = data.user;
  const complaints = data.complaints;
  const pending    = complaints.filter(c => c.status === 'Pending').length;
  const inProgress = complaints.filter(c => c.status === 'In Progress').length;

  // ── Profile grid ──────────────────────────────────────────────
  const grid = `
    <div class="cust-profile-grid">
      <div class="cust-profile-cell">
        <div class="cust-profile-label">User ID</div>
        <div class="cust-profile-value mono">#${u.user_id}</div>
      </div>
      <div class="cust-profile-cell">
        <div class="cust-profile-label">Username</div>
        <div class="cust-profile-value">${escapeHtml(u.username)}</div>
      </div>
      <div class="cust-profile-cell">
        <div class="cust-profile-label">Email</div>
        <div class="cust-profile-value">${escapeHtml(u.email)}</div>
      </div>
      <div class="cust-profile-cell">
        <div class="cust-profile-label">Joined</div>
        <div class="cust-profile-value mono">${fmtDate(u.joined)}</div>
      </div>
      <div class="cust-profile-cell">
        <div class="cust-profile-label">Total Complaints</div>
        <div class="cust-profile-value">${u.complaint_count}</div>
      </div>
      <div class="cust-profile-cell">
        <div class="cust-profile-label">Open Issues</div>
        <div class="cust-profile-value">
          <div class="cust-open-pills">
            <span class="status-badge ${pending > 0 ? 'pending' : ''}"
                  style="${pending === 0 ? 'opacity:.45;' : ''}">${pending} Pending</span>
            <span class="status-badge ${inProgress > 0 ? 'pending' : ''}"
                  style="${inProgress === 0 ? 'opacity:.45;' : ''}">${inProgress} In Progress</span>
          </div>
        </div>
      </div>
    </div>
  `;

  // ── Complaints table ───────────────────────────────────────────
  let table = '';
  if (!complaints.length) {
    table = `<div class="cust-modal-empty">No complaints filed by this customer.</div>`;
  } else {
    const rows = complaints.map(c => {
      const snippet = c.complaint.length > 55
        ? c.complaint.slice(0, 55) + '…'
        : c.complaint;
      return `
        <tr>
          <td class="ticket-no">#${c.ticket_no}</td>
          <td><span class="inline-label">${escapeHtml(c.category)}</span></td>
          <td><span class="priority-badge ${priorityClassFor(c.priority)}">${escapeHtml(c.priority)}</span></td>
          <td><span class="status-badge ${statusClassFor(c.status)}">${escapeHtml(c.status)}</span></td>
          <td style="font-family:var(--font-mono);font-size:0.8rem;color:var(--ink-faint);">${escapeHtml(c.date_month_year)}</td>
          <td class="complaint-text" title="${escapeHtml(c.complaint)}">${escapeHtml(snippet)}</td>
        </tr>
      `;
    }).join('');

    table = `
      <p class="cust-section-head">Complaints (${complaints.length})</p>
      <div style="overflow-x:auto;">
        <table class="complaint-table cust-modal-table" style="min-width:520px;">
          <thead>
            <tr>
              <th>Ticket</th>
              <th>Category</th>
              <th>Priority</th>
              <th>Status</th>
              <th>Date</th>
              <th>Summary</th>
            </tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
    `;
  }

  document.getElementById('cust-modal-body').innerHTML = grid + table;
}

function closeCustomerModal() {
  document.getElementById('cust-modal').classList.remove('open');
  document.body.style.overflow = '';
}

// ─── Init ─────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  if (!adminGuardAndWireNav()) return;

  loadCustomers();

  // Search — debounced 350 ms, same as dashboard
  document.getElementById('cust-search').addEventListener('input', e => {
    clearTimeout(_debounceTimer);
    _debounceTimer = setTimeout(() => {
      _search = e.target.value;
      _page   = 1;
      loadCustomers();
    }, 350);
  });

  document.getElementById('cust-search-clear').addEventListener('click', () => {
    document.getElementById('cust-search').value = '';
    _search = '';
    _page   = 1;
    loadCustomers();
  });

  document.getElementById('cust-prev').addEventListener('click', () => {
    if (_page > 1) { _page--; loadCustomers(); }
  });
  document.getElementById('cust-next').addEventListener('click', () => {
    _page++;
    loadCustomers();
  });

  // Modal close — button, backdrop click, ESC
  document.getElementById('cust-modal-close').addEventListener('click', closeCustomerModal);
  document.getElementById('cust-modal-close-btn').addEventListener('click', closeCustomerModal);
  document.getElementById('cust-modal').addEventListener('click', e => {
    if (e.target.id === 'cust-modal') closeCustomerModal();
  });
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') closeCustomerModal();
  });
});
