// ==========================================================================
// Loopline — admin dashboard logic
// Requires config.js, admin.js loaded first.
// ==========================================================================

const CATEGORY_COLORS = ['#3F8489', '#FFC94A', '#D64545', '#8695A4', '#2C5F63'];
const STATUS_COLORS = { 'Pending': '#FFC94A', 'In Progress': '#3F8489', 'Resolved': '#2C5F63', 'Closed': '#8695A4' };
const PRIORITY_COLORS = { 'Low': '#2C5F63', 'Medium': '#FFC94A', 'High': '#D64545' };

// ---------------- Chart.js polish ----------------
// Chart.js's own defaults (grey gridlines, a black default tooltip,
// the browser's default sans font) read as "generic library chart"
// next to the rest of this dashboard's custom-styled cards - this
// section is the one place that gets a deliberate signature touch
// (the doughnut center-total) plus quiet, consistent polish
// everywhere else (soft gridlines, Inter throughout, ink-toned
// tooltips) rather than a redesign. See docs/DECISIONS.md #24.
if (typeof Chart !== 'undefined') {
  Chart.defaults.font.family = "'Inter', sans-serif";
  Chart.defaults.color = '#8695A4'; // --ink-faint
  Chart.defaults.plugins.tooltip.backgroundColor = '#1B2430'; // --ink
  Chart.defaults.plugins.tooltip.titleFont = { family: 'Inter', size: 12, weight: '600' };
  Chart.defaults.plugins.tooltip.bodyFont = { family: 'Inter', size: 12 };
  Chart.defaults.plugins.tooltip.padding = 10;
  Chart.defaults.plugins.tooltip.cornerRadius = 8;
  Chart.defaults.plugins.tooltip.boxPadding = 4;

  // Signature touch: draws "<value>" + "<label>" centered in a
  // doughnut's hole (e.g. the total complaint count). Opt in per-chart
  // via `options.plugins.centerText = {display: true, value, label}`;
  // does nothing on charts that don't set it (bar charts included).
  Chart.register({
    id: 'centerText',
    afterDraw(chart) {
      const opts = chart.config.options?.plugins?.centerText;
      if (!opts || !opts.display) return;
      // chartArea is undefined until Chart.js has completed layout;
      // during the very first afterDraw call (before first paint) it
      // can be missing. Guard here so a thrown TypeError doesn't kill
      // the draw cycle for ALL four charts - see docs/DECISIONS.md #26.
      if (!chart.chartArea) return;
      const { left, right, top, bottom } = chart.chartArea;
      const { ctx } = chart;
      const centerX = (left + right) / 2;
      const centerY = (top + bottom) / 2;
      ctx.save();
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.font = "700 28px 'Fraunces', serif";
      ctx.fillStyle = '#1B2430';
      ctx.fillText(String(opts.value), centerX, centerY - 10);
      ctx.font = "600 11px 'Inter', sans-serif";
      ctx.fillStyle = '#8695A4';
      ctx.fillText(String(opts.label).toUpperCase(), centerX, centerY + 14);
      ctx.restore();
    },
  });
}

// Shared axis styling for the two bar charts - soft, low-contrast
// gridlines on the value axis only, no axis border line, so the
// chart-card's own border does that job instead of a second one from
// Chart.js right next to it.
function barScale(axis) {
  return {
    beginAtZero: true,
    ticks: { precision: 0, font: { family: 'Inter', size: 11 } },
    grid: { color: '#EDF1F5', drawTicks: false },
    border: { display: false },
  };
}
const CATEGORY_LEGEND = { position: 'bottom', labels: { font: { family: 'Inter', size: 12 }, padding: 14, usePointStyle: true, pointStyle: 'circle' } };

let currentPage = 1;
const PAGE_SIZE = 15;
let lastPageData = { items: [], total: 0, page: 1, page_size: PAGE_SIZE };
const charts = {}; // canvas id -> Chart instance

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str == null ? '' : String(str);
  return div.innerHTML;
}

// ---------------- ML status ----------------
async function loadMlStatus() {
  try {
    const data = await adminFetch('/admin/ml-status');
    const cat = data.category_model;
    const pri = data.priority_model;

    document.getElementById('dot-category').classList.add(cat.available ? 'on' : 'off');
    document.getElementById('metric-category').textContent = cat.available && cat.metrics
      ? `Logistic Regression · ${(cat.metrics.accuracy_vs_keyword_labels * 100).toFixed(1)}% test accuracy`
      : 'Using keyword baseline (no trained model yet)';

    document.getElementById('dot-priority').classList.add(pri.available ? 'on' : 'off');
    document.getElementById('metric-priority').textContent = pri.available && pri.metrics
      ? `${pri.metrics.model.split('(')[0]} · ${(pri.metrics.accuracy_vs_baseline_labels * 100).toFixed(1)}% test accuracy`
      : 'Using rule-based baseline (no trained model yet)';
  } catch (e) {
    console.warn('Could not load ML status', e);
  }
}

// ---------------- Analytics + charts ----------------
function upsertChart(canvasId, config) {
  const ctx = document.getElementById(canvasId);
  if (charts[canvasId]) charts[canvasId].destroy();
  charts[canvasId] = new Chart(ctx, config);
}

async function loadAnalytics() {
  let data;
  try {
    data = await adminFetch('/admin/analytics');
  } catch (e) {
    adminShowToast('Could not load analytics.');
    return;
  }

  document.getElementById('stat-total').textContent = data.total;
  const open = (data.by_status['Pending'] || 0) + (data.by_status['In Progress'] || 0);
  const closed = (data.by_status['Resolved'] || 0) + (data.by_status['Closed'] || 0);
  document.getElementById('stat-open').textContent = open;
  document.getElementById('stat-closed').textContent = closed;

  // Trend pill
  const pill = document.getElementById('trend-pill');
  if (data.trend) {
    const delta = data.trend.delta;
    pill.style.display = 'inline-flex';
    pill.className = 'trend-pill ' + (delta > 0 ? 'up' : delta < 0 ? 'down' : 'flat');
    const arrow = delta > 0 ? '▲' : delta < 0 ? '▼' : '▬';
    pill.textContent = `${arrow} ${delta > 0 ? '+' : ''}${delta} vs last month`;
  } else {
    pill.style.display = 'none';
  }

  // Monthly volume (bar)
  upsertChart('chart-monthly', {
    type: 'bar',
    data: {
      labels: data.monthly_volume.map(m => m.month.slice(2)), // "26-07"
      datasets: [{ data: data.monthly_volume.map(m => m.count), backgroundColor: '#3F8489', borderRadius: 6, maxBarThickness: 34 }]
    },
    options: {
      plugins: { legend: { display: false } },
      scales: { y: barScale('y'), x: { grid: { display: false }, border: { display: false }, ticks: { font: { family: 'Inter', size: 11 } } } }
    }
  });

  // Category distribution (doughnut)
  const catLabels = Object.keys(data.by_category);
  const catTotal = catLabels.reduce((sum, c) => sum + data.by_category[c], 0);
  upsertChart('chart-category', {
    type: 'doughnut',
    data: {
      labels: catLabels,
      datasets: [{ data: catLabels.map(c => data.by_category[c]), backgroundColor: CATEGORY_COLORS, borderColor: '#FFFFFF', borderWidth: 3 }]
    },
    options: {
      cutout: '68%',
      plugins: {
        legend: CATEGORY_LEGEND,
        centerText: { display: true, value: catTotal, label: 'Total' },
      },
    },
  });

  // Priority distribution (bar, ordered Low/Medium/High)
  const priOrder = ['Low', 'Medium', 'High'];
  upsertChart('chart-priority', {
    type: 'bar',
    data: {
      labels: priOrder,
      datasets: [{
        data: priOrder.map(p => data.by_priority[p] || 0),
        backgroundColor: priOrder.map(p => PRIORITY_COLORS[p]),
        borderRadius: 6,
        maxBarThickness: 26,
      }]
    },
    options: {
      indexAxis: 'y',
      plugins: { legend: { display: false } },
      scales: { x: barScale('x'), y: { grid: { display: false }, border: { display: false }, ticks: { font: { family: 'Inter', size: 12, weight: '500' } } } }
    }
  });

  // Status distribution (doughnut)
  const statusLabels = Object.keys(data.by_status);
  const statusTotal = statusLabels.reduce((sum, s) => sum + data.by_status[s], 0);
  upsertChart('chart-status', {
    type: 'doughnut',
    data: {
      labels: statusLabels,
      datasets: [{ data: statusLabels.map(s => data.by_status[s]), backgroundColor: statusLabels.map(s => STATUS_COLORS[s] || '#8695A4'), borderColor: '#FFFFFF', borderWidth: 3 }]
    },
    options: {
      cutout: '68%',
      plugins: {
        legend: CATEGORY_LEGEND,
        centerText: { display: true, value: statusTotal, label: 'Total' },
      },
    },
  });
}

// ---------------- Categories (for filter + manual entry dropdowns) ----------------
async function loadCategoryOptions() {
  let categories = [];
  try {
    categories = await adminFetch('/categories');
  } catch (e) {
    categories = ['Billing', 'Financial', 'Technical', 'Service', 'Others'];
  }
  const filterSel = document.getElementById('filter-category');
  const manualSel = document.getElementById('m-category');
  categories.forEach(cat => {
    const opt1 = document.createElement('option'); opt1.value = cat; opt1.textContent = cat;
    filterSel.appendChild(opt1);
    const opt2 = document.createElement('option'); opt2.value = cat; opt2.textContent = cat;
    manualSel.appendChild(opt2);
  });
  return categories;
}

// ---------------- Table ----------------
function buildQueryString() {
  const params = new URLSearchParams();
  params.set('page', currentPage);
  params.set('page_size', PAGE_SIZE);
  const category = document.getElementById('filter-category').value;
  const priority = document.getElementById('filter-priority').value;
  const status = document.getElementById('filter-status').value;
  const search = document.getElementById('filter-search').value.trim();
  if (category) params.set('category', category);
  if (priority) params.set('priority', priority);
  if (status) params.set('status', status);
  if (search) params.set('search', search);
  return params.toString();
}

async function loadTable() {
  let data;
  try {
    data = await adminFetch(`/admin/complaints?${buildQueryString()}`);
  } catch (e) {
    adminShowToast('Could not load complaints.');
    return;
  }
  lastPageData = data;
  renderTable(data.items);
  renderPagination(data);
}

function statusClassFor(status) {
  return ['Resolved', 'Closed'].includes(status) ? 'resolved' : 'pending';
}
function priorityClassFor(priority) {
  return (priority || 'low').toLowerCase();
}

function renderTable(items) {
  const tbody = document.getElementById('admin-tbody');
  const emptyEl = document.getElementById('admin-table-empty');
  tbody.innerHTML = '';

  if (!items.length) {
    emptyEl.style.display = 'block';
    return;
  }
  emptyEl.style.display = 'none';

  items.forEach(c => {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td class="ticket-no">#${c.ticket_no}</td>
      <td>
        <select class="inline-select" data-field="category" data-ticket="${c.ticket_no}">
          ${['Billing','Financial','Technical','Service','Others'].map(cat =>
            `<option value="${cat}" ${cat === c.category ? 'selected' : ''}>${cat}</option>`).join('')}
        </select>
      </td>
      <td>
        <select class="inline-select" data-field="priority" data-ticket="${c.ticket_no}">
          ${['Low','Medium','High'].map(p =>
            `<option value="${p}" ${p === c.priority ? 'selected' : ''}>${p}</option>`).join('')}
        </select>
      </td>
      <td class="complaint-text" title="${escapeHtml(c.complaint)}">${escapeHtml(c.complaint)}</td>
      <td>${escapeHtml(c.date_month_year)}</td>
      <td>${escapeHtml(c.city || '—')}</td>
      <td>${escapeHtml(c.received_via)}</td>
      <td>
        <select class="inline-select" data-field="status" data-ticket="${c.ticket_no}">
          ${['Pending','In Progress','Resolved','Closed'].map(s =>
            `<option value="${s}" ${s === c.status ? 'selected' : ''}>${s}</option>`).join('')}
        </select>
      </td>
      <td>
        <button type="button" class="row-btn row-btn-view" data-action="view" data-ticket="${c.ticket_no}">👁 View</button>
      </td>
    `;
    tbody.appendChild(tr);
  });

  tbody.querySelectorAll('[data-action="view"]').forEach(btn => {
    btn.addEventListener('click', () => openViewModal(Number(btn.dataset.ticket)));
  });
  tbody.querySelectorAll('select.inline-select').forEach(sel => {
    sel.addEventListener('change', () => handleInlineEdit(sel));
  });
}

async function handleInlineEdit(selectEl) {
  const ticket = selectEl.dataset.ticket;
  const field = selectEl.dataset.field;
  const value = selectEl.value;
  selectEl.disabled = true;
  try {
    await adminFetch(`/admin/complaints/${ticket}`, {
      method: 'PATCH',
      body: JSON.stringify({ [field]: value })
    });
    adminShowToast(`Ticket #${ticket} updated.`);
    loadAnalytics(); // counts may have shifted
  } catch (e) {
    adminShowToast(e.message || 'Update failed.');
  } finally {
    selectEl.disabled = false;
  }
}

function renderPagination(data) {
  const totalPages = Math.max(1, Math.ceil(data.total / data.page_size));
  document.getElementById('page-info').textContent = `Page ${data.page} of ${totalPages} (${data.total} total)`;
  document.getElementById('page-prev').disabled = data.page <= 1;
  document.getElementById('page-next').disabled = data.page >= totalPages;
}

// ---------------- View modal ----------------
function openViewModal(ticketNo) {
  const c = lastPageData.items.find(i => i.ticket_no === ticketNo);
  if (!c) return;
  document.getElementById('view-body').innerHTML = `
    <div class="view-grid">
      <div><strong>Ticket #</strong><div>${c.ticket_no}</div></div>
      <div><strong>Status</strong><div><span class="status-badge ${statusClassFor(c.status)}">${escapeHtml(c.status)}</span></div></div>
      <div><strong>Category</strong><div>${escapeHtml(c.category)}</div></div>
      <div><strong>Priority</strong><div><span class="priority-badge ${priorityClassFor(c.priority)}">${escapeHtml(c.priority)}</span></div></div>
      <div><strong>Date</strong><div>${escapeHtml(c.date_month_year)} ${escapeHtml(c.time || '')}</div></div>
      <div><strong>Received via</strong><div>${escapeHtml(c.received_via)}</div></div>
      <div><strong>City</strong><div>${escapeHtml(c.city || '—')}</div></div>
      <div><strong>State</strong><div>${escapeHtml(c.state || '—')}</div></div>
      <div><strong>Zip</strong><div>${escapeHtml(c.zipcode || '—')}</div></div>
      <div><strong>Linked customer</strong><div>${c.user_id ? `User #${c.user_id}` : 'None (manual entry)'}</div></div>
    </div>
    <div class="view-complaint-block">${escapeHtml(c.complaint)}</div>
  `;
  document.getElementById('view-modal').classList.add('open');
  document.body.style.overflow = 'hidden';
}
function closeViewModal() {
  document.getElementById('view-modal').classList.remove('open');
  document.body.style.overflow = '';
}

// ---------------- Manual entry modal ----------------
function openManualModal() {
  document.getElementById('manual-form').reset();
  document.getElementById('manual-modal').classList.add('open');
  document.body.style.overflow = 'hidden';
}
function closeManualModal() {
  document.getElementById('manual-modal').classList.remove('open');
  document.body.style.overflow = '';
}

// ---------------- Wiring ----------------
function debounce(fn, ms) {
  let t;
  return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
}

document.addEventListener('DOMContentLoaded', async () => {
  const session = adminGuardAndWireNav();
  if (!session) return;

  await loadCategoryOptions();
  loadMlStatus();
  loadAnalytics();
  loadTable();

  document.getElementById('filter-category').addEventListener('change', () => { currentPage = 1; loadTable(); });
  document.getElementById('filter-priority').addEventListener('change', () => { currentPage = 1; loadTable(); });
  document.getElementById('filter-status').addEventListener('change', () => { currentPage = 1; loadTable(); });
  document.getElementById('filter-search').addEventListener('input', debounce(() => { currentPage = 1; loadTable(); }, 350));
  document.getElementById('filter-clear').addEventListener('click', () => {
    document.getElementById('filter-category').value = '';
    document.getElementById('filter-priority').value = '';
    document.getElementById('filter-status').value = '';
    document.getElementById('filter-search').value = '';
    currentPage = 1;
    loadTable();
  });

  document.getElementById('page-prev').addEventListener('click', () => { if (currentPage > 1) { currentPage--; loadTable(); } });
  document.getElementById('page-next').addEventListener('click', () => {
    const totalPages = Math.max(1, Math.ceil(lastPageData.total / lastPageData.page_size));
    if (currentPage < totalPages) { currentPage++; loadTable(); }
  });

  document.getElementById('view-close').addEventListener('click', closeViewModal);
  document.getElementById('view-close-btn').addEventListener('click', closeViewModal);
  document.getElementById('view-modal').addEventListener('click', (e) => { if (e.target.id === 'view-modal') closeViewModal(); });

  document.getElementById('btn-new-complaint-admin').addEventListener('click', openManualModal);
  document.getElementById('manual-close').addEventListener('click', closeManualModal);
  document.getElementById('manual-cancel').addEventListener('click', closeManualModal);
  document.getElementById('manual-modal').addEventListener('click', (e) => { if (e.target.id === 'manual-modal') closeManualModal(); });

  document.getElementById('manual-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const body = {
      complaint: document.getElementById('m-complaint').value.trim(),
      category: document.getElementById('m-category').value || null,
      priority: document.getElementById('m-priority').value || null,
      received_via: document.getElementById('m-received-via').value,
      status: document.getElementById('m-status').value,
      city: document.getElementById('m-city').value.trim() || null,
      state: document.getElementById('m-state').value.trim() || null,
      zipcode: document.getElementById('m-zip').value.trim() || null,
    };
    if (!body.complaint) { adminShowToast('Please enter a complaint description.'); return; }
    try {
      const created = await adminFetch('/admin/complaints', { method: 'POST', body: JSON.stringify(body) });
      adminShowToast(`Complaint #${created.ticket_no} added.`);
      closeManualModal();
      currentPage = 1;
      loadTable();
      loadAnalytics();
    } catch (err) {
      adminShowToast(err.message || 'Could not add complaint.');
    }
  });

  document.addEventListener('keydown', (e) => {
    if (e.key !== 'Escape') return;
    if (document.getElementById('view-modal').classList.contains('open')) closeViewModal();
    if (document.getElementById('manual-modal').classList.contains('open')) closeManualModal();
  });
});
