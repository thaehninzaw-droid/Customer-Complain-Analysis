// ==========================================================================
// Loopline — admin-customers.js
// Requires config.js (API_BASE) and admin.js (adminFetch,
// adminGuardAndWireNav) loaded first.
// ==========================================================================
'use strict';

let _page          = 1;
const PAGE_SIZE    = 20;
let _search        = '';
let _debounceTimer = null;

// ─── Utilities ────────────────────────────────────────────────────────────────
function escapeHtml(s) {
  const d = document.createElement('div');
  d.textContent = s == null ? '' : String(s);
  return d.innerHTML;
}
function statusClassFor(s)  { return ['Resolved','Closed'].includes(s) ? 'resolved' : 'pending'; }
function priorityClassFor(p){ return (p || 'low').toLowerCase(); }
function fmtDate(iso)       { return iso ? String(iso).slice(0,10) : '—'; }

// ─── Stat cards ───────────────────────────────────────────────────────────────
function updateStats(data) {
  document.getElementById('stat-total').textContent = data.total;
  // Page-scoped; asterisk when there are more pages
  const suf = data.total > PAGE_SIZE ? '*' : '';
  document.getElementById('stat-open').textContent =
    data.items.filter(u => u.complaint_count > 0).length + suf;
  document.getElementById('stat-none').textContent =
    data.items.filter(u => u.complaint_count === 0).length + suf;
}

// ─── Customer list ────────────────────────────────────────────────────────────
async function loadCustomers() {
  const tbody  = document.getElementById('cust-tbody');
  const empty  = document.getElementById('cust-empty');
  const loader = document.getElementById('cust-loading');
  const pag    = document.getElementById('cust-pagination');

  tbody.innerHTML    = '';
  empty.style.display  = 'none';
  loader.style.display = 'block';
  pag.style.display    = 'none';

  const params = new URLSearchParams({ page: _page, page_size: PAGE_SIZE });
  if (_search.trim()) params.set('search', _search.trim());

  try {
    const data = await adminFetch(`/admin/customers?${params}`);
    loader.style.display = 'none';
    updateStats(data);

    if (!data.items.length) {
      empty.textContent    = _search ? 'No customers match your search.' : 'No customer accounts yet.';
      empty.style.display  = 'block';
      return;
    }

    // Build all rows in a fragment — one DOM insertion
    const frag = document.createDocumentFragment();
    data.items.forEach(u => {
      const tr = document.createElement('tr');
      const pillClass = u.complaint_count === 0 ? 'zero' : '';
      tr.innerHTML = `
        <td class="ticket-no" style="color:var(--ink-faint);font-weight:400;">#${u.user_id}</td>
        <td style="font-weight:600;">${escapeHtml(u.username)}</td>
        <td style="color:var(--ink-faint);font-size:0.875rem;">${escapeHtml(u.email)}</td>
        <td style="font-family:var(--font-mono);font-size:0.82rem;color:var(--ink-faint);">${fmtDate(u.joined)}</td>
        <td><span class="count-pill ${pillClass}">${u.complaint_count}</span></td>
        <td>
          <button type="button" class="row-btn row-btn-view"
                  data-action="view-customer"
                  data-userid="${u.user_id}"
                  data-username="${escapeHtml(u.username)}">
            <svg viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg"
                 style="width:12px;height:12px;margin-right:3px;vertical-align:-1px;">
              <circle cx="8" cy="5.5" r="2.25" stroke="currentColor" stroke-width="1.5"/>
              <path d="M2.5 13.5c0-3 2.5-4.5 5.5-4.5s5.5 1.5 5.5 4.5"
                    stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
            </svg>View
          </button>
        </td>`;
      frag.appendChild(tr);
    });
    tbody.appendChild(frag);

    // Single delegated listener — replaces the entire tbody on each load
    // so we re-attach once here rather than N times per row.
    tbody.onclick = e => {
      const btn = e.target.closest('[data-action="view-customer"]');
      if (btn) openCustomerModal(Number(btn.dataset.userid), btn.dataset.username);
    };

    // Pagination
    const totalPages = Math.max(1, Math.ceil(data.total / data.page_size));
    document.getElementById('cust-page-info').textContent =
      `Page ${data.page} of ${totalPages}`;
    document.getElementById('cust-prev').disabled = data.page <= 1;
    document.getElementById('cust-next').disabled = data.page >= totalPages;
    pag.style.display = 'flex';

  } catch (err) {
    loader.style.display = 'none';
    empty.textContent    = err.message || 'Failed to load customers.';
    empty.style.display  = 'block';
  }
}

// ─── Customer detail modal ────────────────────────────────────────────────────
async function openCustomerModal(userId, username) {
  const modal   = document.getElementById('cust-modal');
  const titleEl = document.getElementById('cust-modal-title');
  const bodyEl  = document.getElementById('cust-modal-body');

  titleEl.textContent = username;
  bodyEl.innerHTML    =
    '<p style="text-align:center;color:var(--ink-faint);padding:2.5rem 0;">Loading…</p>';
  modal.classList.add('open');
  document.body.style.overflow = 'hidden';

  try {
    const data = await adminFetch(`/admin/customers/${userId}`);
    renderModal(data);
  } catch (err) {
    bodyEl.innerHTML =
      `<p style="color:var(--danger);padding:1rem 0;">${escapeHtml(err.message || 'Could not load profile.')}</p>`;
  }
}

function renderModal(data) {
  const u          = data.user;
  const complaints = data.complaints;
  const pending    = complaints.filter(c => c.status === 'Pending').length;
  const inProg     = complaints.filter(c => c.status === 'In Progress').length;

  // ── Profile grid — identical pattern to the complaint detail modal ────
  // Bold label on top, value directly below, 2-col grid.
  // Open-issues row spans both columns (col 1–2) via a wrapper div.
  const profileGrid = `
    <div class="view-grid" style="margin-bottom:20px;">
      <div><strong>User ID</strong>
           <div style="font-family:var(--font-mono);">#${u.user_id}</div></div>
      <div><strong>Username</strong>
           <div>${escapeHtml(u.username)}</div></div>
      <div><strong>Email</strong>
           <div>${escapeHtml(u.email)}</div></div>
      <div><strong>Joined</strong>
           <div style="font-family:var(--font-mono);">${fmtDate(u.joined)}</div></div>
      <div><strong>Total complaints</strong>
           <div>${u.complaint_count}</div></div>
      <div><strong>Open issues</strong>
           <div style="display:flex;gap:6px;flex-wrap:wrap;margin-top:2px;">
             <span class="status-badge ${pending > 0 ? 'pending' : ''}"
                   style="${pending === 0 ? 'opacity:.38;' : ''}">${pending} Pending</span>
             <span class="status-badge ${inProg > 0 ? 'pending' : ''}"
                   style="${inProg === 0 ? 'opacity:.38;' : ''}">${inProg} In Progress</span>
           </div></div>
    </div>`;

  // ── Complaints section ────────────────────────────────────────────────
  let table = '';
  if (!complaints.length) {
    table = `<div class="cust-modal-empty">No complaints filed by this customer.</div>`;
  } else {
    const rows = complaints.map(c => {
      const snippet = c.complaint.length > 52
        ? c.complaint.slice(0, 52) + '…' : c.complaint;
      return `<tr>
        <td class="ticket-no">#${c.ticket_no}</td>
        <td><span class="inline-label">${escapeHtml(c.category)}</span></td>
        <td><span class="priority-badge ${priorityClassFor(c.priority)}">${escapeHtml(c.priority)}</span></td>
        <td><span class="status-badge ${statusClassFor(c.status)}">${escapeHtml(c.status)}</span></td>
        <td style="font-family:var(--font-mono);font-size:0.79rem;color:var(--ink-faint);white-space:nowrap;">${escapeHtml(c.date_month_year)}</td>
        <td class="complaint-text" title="${escapeHtml(c.complaint)}">${escapeHtml(snippet)}</td>
      </tr>`;
    }).join('');

    table = `
      <p class="cust-section-label">Complaints (${complaints.length})</p>
      <div style="overflow-x:auto;">
        <table class="complaint-table cust-complaints-table" style="min-width:500px;">
          <thead><tr>
            <th>Ticket</th><th>Category</th><th>Priority</th>
            <th>Status</th><th>Date</th><th>Summary</th>
          </tr></thead>
          <tbody>${rows}</tbody>
        </table>
      </div>`;
  }

  document.getElementById('cust-modal-body').innerHTML = profileGrid + table;
}

function closeModal() {
  document.getElementById('cust-modal').classList.remove('open');
  document.body.style.overflow = '';
}

// ─── Init ─────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  if (!adminGuardAndWireNav()) return;

  loadCustomers();

  // Debounced search — 350 ms, same as dashboard
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

  document.getElementById('cust-modal-close').addEventListener('click', closeModal);
  document.getElementById('cust-modal-close-btn').addEventListener('click', closeModal);
  document.getElementById('cust-modal').addEventListener('click', e => {
    if (e.target.id === 'cust-modal') closeModal();
  });
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') closeModal();
  });
});
