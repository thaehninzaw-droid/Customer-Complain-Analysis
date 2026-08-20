// ==========================================================================
// Loopline — admin customers page logic
// Requires config.js, admin.js loaded first.
// ==========================================================================

'use strict';

// ─── State ───────────────────────────────────────────────────────────────────
let _page     = 1;
const PAGE_SIZE = 20;
let _search   = '';
let _debounceTimer = null;

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str == null ? '' : String(str);
  return div.innerHTML;
}

function statusClassFor(status) {
  return ['Resolved', 'Closed'].includes(status) ? 'resolved' : 'pending';
}

function priorityClassFor(priority) {
  return (priority || 'low').toLowerCase();
}

function formatDate(iso) {
  if (!iso) return '—';
  // Show just the date portion (YYYY-MM-DD) regardless of timezone offset
  return iso.slice(0, 10);
}

// ─── Load + render customer list ─────────────────────────────────────────────
async function loadCustomers() {
  const tbody   = document.getElementById('cust-tbody');
  const emptyEl = document.getElementById('cust-empty');
  const loadEl  = document.getElementById('cust-loading');
  const pagBar  = document.getElementById('cust-pagination');

  tbody.innerHTML = '';
  emptyEl.style.display = 'none';
  loadEl.style.display  = 'block';
  pagBar.style.display  = 'none';

  const params = new URLSearchParams({ page: _page, page_size: PAGE_SIZE });
  if (_search.trim()) params.set('search', _search.trim());

  try {
    const data = await adminFetch(`/admin/customers?${params}`);
    loadEl.style.display = 'none';

    if (!data.items.length) {
      emptyEl.style.display = 'block';
      return;
    }

    data.items.forEach(u => {
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td class="ticket-no" style="font-family:var(--font-mono);">#${u.user_id}</td>
        <td><strong>${escapeHtml(u.username)}</strong></td>
        <td style="color:var(--ink-faint); font-size:0.88rem;">${escapeHtml(u.email)}</td>
        <td style="font-size:0.85rem; color:var(--ink-faint); font-family:var(--font-mono);">${formatDate(u.joined)}</td>
        <td>
          <span class="inline-label ${u.complaint_count > 0 ? '' : 'resolved'}"
                style="min-width:2rem; text-align:center;">
            ${u.complaint_count}
          </span>
        </td>
        <td>
          <button type="button" class="row-btn row-btn-view"
                  data-action="view-customer"
                  data-userid="${u.user_id}"
                  data-username="${escapeHtml(u.username)}">
            👤 View
          </button>
        </td>
      `;
      tbody.appendChild(tr);
    });

    // Wire view buttons
    tbody.querySelectorAll('[data-action="view-customer"]').forEach(btn => {
      btn.addEventListener('click', () =>
        openCustomerModal(Number(btn.dataset.userid), btn.dataset.username)
      );
    });

    // Pagination
    const totalPages = Math.max(1, Math.ceil(data.total / data.page_size));
    document.getElementById('cust-page-info').textContent =
      `Page ${data.page} of ${totalPages} (${data.total} customer${data.total !== 1 ? 's' : ''})`;
    document.getElementById('cust-prev').disabled = data.page <= 1;
    document.getElementById('cust-next').disabled = data.page >= totalPages;
    pagBar.style.display = 'flex';

  } catch (e) {
    loadEl.style.display = 'none';
    emptyEl.textContent  = e.message || 'Failed to load customers.';
    emptyEl.style.display = 'block';
  }
}

// ─── Customer detail modal ────────────────────────────────────────────────────
async function openCustomerModal(userId, username) {
  document.getElementById('cust-modal-title').textContent = `Customer: ${username}`;
  document.getElementById('cust-modal-body').innerHTML =
    '<p style="color:var(--ink-faint); padding:1rem 0;">Loading…</p>';
  document.getElementById('cust-modal').classList.add('open');
  document.body.style.overflow = 'hidden';

  try {
    const data = await adminFetch(`/admin/customers/${userId}`);
    renderCustomerModal(data);
  } catch (e) {
    document.getElementById('cust-modal-body').innerHTML =
      `<p style="color:var(--danger);">${escapeHtml(e.message || 'Failed to load customer details.')}</p>`;
  }
}

function renderCustomerModal(data) {
  const u = data.user;
  const complaints = data.complaints;

  // Summary counts
  const pending    = complaints.filter(c => c.status === 'Pending').length;
  const inProgress = complaints.filter(c => c.status === 'In Progress').length;

  // Profile block
  let html = `
    <div class="view-grid" style="margin-bottom:1.25rem;">
      <div><strong>User ID</strong><div style="font-family:var(--font-mono);">#${u.user_id}</div></div>
      <div><strong>Username</strong><div>${escapeHtml(u.username)}</div></div>
      <div><strong>Email</strong><div style="font-size:0.9rem;">${escapeHtml(u.email)}</div></div>
      <div><strong>Joined</strong><div style="font-family:var(--font-mono); font-size:0.88rem;">${formatDate(u.joined)}</div></div>
      <div><strong>Total complaints</strong><div>${u.complaint_count}</div></div>
      <div><strong>Open</strong>
        <div>
          <span class="inline-label pending" style="margin-right:4px;">${pending} Pending</span>
          <span class="inline-label pending">${inProgress} In Progress</span>
        </div>
      </div>
    </div>
  `;

  // Complaints table
  if (!complaints.length) {
    html += `<p style="color:var(--ink-faint); font-size:0.9rem;">No complaints filed by this customer.</p>`;
  } else {
    html += `
      <h3 style="font-size:0.9rem; font-weight:600; color:var(--ink-faint); text-transform:uppercase;
                 letter-spacing:.05em; margin:0 0 0.75rem;">Complaints (${complaints.length})</h3>
      <div style="overflow-x:auto;">
        <table class="complaint-table" style="min-width:560px;">
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
          <tbody>
    `;
    complaints.forEach(c => {
      const snippet = c.complaint.length > 60
        ? c.complaint.slice(0, 60) + '…'
        : c.complaint;
      html += `
        <tr>
          <td class="ticket-no" style="font-family:var(--font-mono);">#${c.ticket_no}</td>
          <td><span class="inline-label">${escapeHtml(c.category)}</span></td>
          <td><span class="priority-badge ${priorityClassFor(c.priority)}">${escapeHtml(c.priority)}</span></td>
          <td><span class="status-badge ${statusClassFor(c.status)}">${escapeHtml(c.status)}</span></td>
          <td style="font-size:0.82rem; font-family:var(--font-mono); color:var(--ink-faint);">${escapeHtml(c.date_month_year)}</td>
          <td class="complaint-text" title="${escapeHtml(c.complaint)}">${escapeHtml(snippet)}</td>
        </tr>
      `;
    });
    html += `</tbody></table></div>`;
  }

  document.getElementById('cust-modal-body').innerHTML = html;
}

function closeCustomerModal() {
  document.getElementById('cust-modal').classList.remove('open');
  document.body.style.overflow = '';
}

// ─── Init ─────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  if (!adminGuardAndWireNav()) return;

  loadCustomers();

  // Search — debounced
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

  // Pagination
  document.getElementById('cust-prev').addEventListener('click', () => {
    if (_page > 1) { _page--; loadCustomers(); }
  });
  document.getElementById('cust-next').addEventListener('click', () => {
    _page++;
    loadCustomers();
  });

  // Modal close
  document.getElementById('cust-modal-close').addEventListener('click', closeCustomerModal);
  document.getElementById('cust-modal-close-btn').addEventListener('click', closeCustomerModal);
  document.getElementById('cust-modal').addEventListener('click', e => {
    if (e.target.id === 'cust-modal') closeCustomerModal();
  });

  // ESC key
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') closeCustomerModal();
  });
});
