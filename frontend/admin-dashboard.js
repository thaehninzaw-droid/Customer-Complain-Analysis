// ==========================================================================
// Loopline — admin dashboard logic
// Requires config.js, admin.js loaded first.
// Charts: pure SVG (no Chart.js / no CDN — works on file:// and any server)
// ==========================================================================

'use strict';

// ─── Colour tokens (match original Chart.js palette exactly) ────────────────
const CATEGORY_COLORS = ['#3F8489','#FFC94A','#D64545','#8695A4','#2C5F63','#a78bfa'];
const STATUS_COLORS   = { 'Pending':'#FFC94A','In Progress':'#3F8489','Resolved':'#2C5F63','Closed':'#8695A4' };
const PRIORITY_COLORS = { 'Low':'#2C5F63','Medium':'#FFC94A','High':'#D64545' };

// ─── Comcast baseline data (2,224 complaints — 2025 dataset) ────────────────
const BASELINE = {
  total: 2224,
  open: 847,
  closed: 1377,
  trend: { delta: -981 },
  monthly_volume: [
    {month:'25-01',count:215},{month:'25-02',count:198},{month:'25-03',count:231},
    {month:'25-04',count:187},{month:'25-05',count:203},{month:'25-06',count:176},
    {month:'25-07',count:189},{month:'25-08',count:162},{month:'25-09',count:194},
    {month:'25-10',count:208},{month:'25-11',count:148},{month:'25-12',count:113},
  ],
  by_category: {
    'Billing':612,'Financial':248,'Technical':498,'Service':387,'Others':479,
  },
  by_priority: { 'Low':704,'Medium':889,'High':631 },
  by_status:   { 'Pending':312,'In Progress':535,'Resolved':1021,'Closed':356 },
};

// ─── State ───────────────────────────────────────────────────────────────────
let _currentSource = 'baseline'; // 'baseline' | 'live'
let _liveData = null;            // cached result from /admin/analytics

// ─── Pagination / table (unchanged from original) ───────────────────────────
let currentPage = 1;
const PAGE_SIZE = 15;
let lastPageData = { items:[], total:0, page:1, page_size:PAGE_SIZE };

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str == null ? '' : String(str);
  return div.innerHTML;
}

// ─── Tooltip ─────────────────────────────────────────────────────────────────
const _tt = () => document.getElementById('lp-tooltip');
function ttShow(e, text) {
  const t = _tt(); if (!t) return;
  t.textContent = text; t.style.opacity = '1'; ttMove(e);
}
function ttMove(e) {
  const t = _tt(); if (!t) return;
  t.style.left = Math.min(e.clientX + 14, window.innerWidth - 200) + 'px';
  t.style.top  = (e.clientY - 34) + 'px';
}
function ttHide() { const t = _tt(); if (t) t.style.opacity = '0'; }

// ─── SVG helper ──────────────────────────────────────────────────────────────
function svgEl(tag, attrs) {
  const el = document.createElementNS('http://www.w3.org/2000/svg', tag);
  for (const [k,v] of Object.entries(attrs || {})) el.setAttribute(k, String(v));
  return el;
}

// ─── SVG: vertical bar chart (Monthly Volume) ────────────────────────────────
function svgBarChart(hostId, labels, values, color) {
  const host = document.getElementById(hostId);
  if (!host) return;

  const W=760, H=200, pL=36, pR=10, pT=14, pB=36;
  const cW = W-pL-pR, cH = H-pT-pB;
  const max = Math.max(...values, 1);
  const cols = labels.length;
  const colW = cW / cols;
  const barW = Math.min(colW * 0.55, 38);
  const GRID = 5;

  const svg = svgEl('svg', { viewBox:`0 0 ${W} ${H}`, style:'overflow:visible' });

  // grid + Y labels
  for (let i = 0; i <= GRID; i++) {
    const val = Math.round(max / GRID * (GRID - i));
    const y   = pT + (cH / GRID) * i;
    svg.appendChild(svgEl('line', { x1:pL, y1:y, x2:W-pR, y2:y,
      stroke:'#EDF1F5', 'stroke-width':1, 'stroke-dasharray': i===GRID?'0':'3 3' }));
    const lbl = svgEl('text', { x:pL-5, y:y+4, 'text-anchor':'end',
      fill:'#8695A4', 'font-size':10, 'font-family':'Inter,sans-serif' });
    lbl.textContent = val >= 1000 ? (val/1000).toFixed(1)+'k' : val;
    svg.appendChild(lbl);
  }

  // bars
  labels.forEach((label, i) => {
    const v  = values[i];
    const bH = Math.max((v / max) * cH, 2);
    const x  = pL + i * colW + (colW - barW) / 2;
    const y  = pT + cH - bH;

    const rect = svgEl('rect', { x, y, width:barW, height:bH, rx:4,
      fill:color || '#3F8489', opacity:.88, style:'cursor:pointer;transition:opacity .12s' });
    rect.addEventListener('mouseenter', e => { rect.setAttribute('opacity',1); ttShow(e, `${label}: ${v.toLocaleString()}`); });
    rect.addEventListener('mousemove',  ttMove);
    rect.addEventListener('mouseleave', () => { rect.setAttribute('opacity',.88); ttHide(); });
    svg.appendChild(rect);

    const xlbl = svgEl('text', { x: x+barW/2, y: pT+cH+16, 'text-anchor':'middle',
      fill:'#8695A4', 'font-size':10, 'font-family':'Inter,sans-serif' });
    xlbl.textContent = label;
    svg.appendChild(xlbl);
  });

  host.innerHTML = '';
  host.appendChild(svg);
}

// ─── SVG: donut chart (Category / Status) ────────────────────────────────────
function svgDonutChart(hostId, slices) {
  const host = document.getElementById(hostId);
  if (!host) return;

  const S=180, cx=S/2, cy=S/2, OR=70, IR=44;
  const total = slices.reduce((s,sl) => s + sl.value, 0);

  const svg = svgEl('svg', { viewBox:`0 0 ${S} ${S}`, style:`width:${S}px;height:${S}px;flex-shrink:0` });

  let angle = -Math.PI / 2;
  slices.forEach(sl => {
    if (!sl.value) return;
    const sweep = (sl.value / total) * 2 * Math.PI;
    const end   = angle + sweep;
    const x1=cx+OR*Math.cos(angle), y1=cy+OR*Math.sin(angle);
    const x2=cx+OR*Math.cos(end),   y2=cy+OR*Math.sin(end);
    const ix1=cx+IR*Math.cos(end),  iy1=cy+IR*Math.sin(end);
    const ix2=cx+IR*Math.cos(angle),iy2=cy+IR*Math.sin(angle);
    const la = sweep > Math.PI ? 1 : 0;

    const path = svgEl('path', {
      d:`M${x1} ${y1} A${OR} ${OR} 0 ${la} 1 ${x2} ${y2} L${ix1} ${iy1} A${IR} ${IR} 0 ${la} 0 ${ix2} ${iy2}Z`,
      fill:sl.color, opacity:.9, style:'cursor:pointer;transition:opacity .12s'
    });
    path.addEventListener('mouseenter', e => {
      path.setAttribute('opacity',1);
      ttShow(e, `${sl.label}: ${sl.value.toLocaleString()} (${((sl.value/total)*100).toFixed(1)}%)`);
    });
    path.addEventListener('mousemove',  ttMove);
    path.addEventListener('mouseleave', () => { path.setAttribute('opacity',.9); ttHide(); });
    svg.appendChild(path);
    angle = end;
  });

  // center text (signature: value + "TOTAL" label, matches original Chart.js plugin)
  const disp = total >= 1000 ? (total/1000).toFixed(1)+'k' : String(total);
  const tVal = svgEl('text', { x:cx, y:cy-5, 'text-anchor':'middle', 'dominant-baseline':'middle',
    fill:'#1B2430', 'font-size':20, 'font-weight':700, 'font-family':'Fraunces,serif' });
  tVal.textContent = disp;
  svg.appendChild(tVal);
  const tLbl = svgEl('text', { x:cx, y:cy+16, 'text-anchor':'middle',
    fill:'#8695A4', 'font-size':9, 'font-weight':600, 'font-family':'Inter,sans-serif',
    'letter-spacing':'.8' });
  tLbl.textContent = 'TOTAL';
  svg.appendChild(tLbl);

  // Legend
  const legend = document.createElement('div');
  legend.className = 'donut-legend';
  slices.forEach(sl => {
    const item = document.createElement('div');
    item.className = 'donut-legend-item';
    item.innerHTML = `
      <span class="donut-legend-swatch" style="background:${sl.color}"></span>
      <span>${escapeHtml(sl.label)}</span>
      <span style="color:#8695A4;margin-left:auto">${((sl.value/total)*100).toFixed(0)}%</span>
    `;
    legend.appendChild(item);
  });

  const wrap = document.createElement('div');
  wrap.className = 'donut-wrap';
  const box = document.createElement('div');
  box.className = 'donut-svg-box';
  box.appendChild(svg);
  wrap.appendChild(box);
  wrap.appendChild(legend);

  host.innerHTML = '';
  host.appendChild(wrap);
}

// ─── SVG: horizontal bar chart (Priority) ────────────────────────────────────
function svgHBarChart(hostId, labels, values, colors) {
  const host = document.getElementById(hostId);
  if (!host) return;

  const W=760, pL=70, pR=60, pT=10, pB=10;
  const barH=26, gap=14;
  const H = pT + labels.length*(barH+gap) - gap + pB;
  const cW = W-pL-pR;
  const max = Math.max(...values, 1);
  const total = values.reduce((a,b)=>a+b, 0);

  const svg = svgEl('svg', { viewBox:`0 0 ${W} ${H}`, style:'overflow:visible' });

  labels.forEach((label, i) => {
    const y   = pT + i*(barH+gap);
    const fillW = (values[i]/max)*cW;

    // track
    svg.appendChild(svgEl('rect', { x:pL, y, width:cW, height:barH, rx:4, fill:'#EDF1F5' }));

    // fill
    const bar = svgEl('rect', { x:pL, y, width:Math.max(fillW,4), height:barH, rx:4,
      fill:colors[i]||'#3F8489', opacity:.88, style:'cursor:pointer;transition:opacity .12s' });
    bar.addEventListener('mouseenter', e => {
      bar.setAttribute('opacity',1);
      const pct = total ? ((values[i]/total)*100).toFixed(1) : 0;
      ttShow(e, `${label}: ${values[i].toLocaleString()} (${pct}%)`);
    });
    bar.addEventListener('mousemove',  ttMove);
    bar.addEventListener('mouseleave', () => { bar.setAttribute('opacity',.88); ttHide(); });
    svg.appendChild(bar);

    // left label
    const llbl = svgEl('text', { x:pL-8, y:y+barH/2, 'text-anchor':'end', 'dominant-baseline':'middle',
      fill:'#4a5568', 'font-size':12, 'font-weight':500, 'font-family':'Inter,sans-serif' });
    llbl.textContent = label;
    svg.appendChild(llbl);

    // right value
    const vlbl = svgEl('text', { x:pL+fillW+8, y:y+barH/2, 'dominant-baseline':'middle',
      fill:'#8695A4', 'font-size':11, 'font-family':'Inter,sans-serif' });
    const pct = total ? ((values[i]/total)*100).toFixed(0) : 0;
    vlbl.textContent = `${values[i].toLocaleString()} (${pct}%)`;
    svg.appendChild(vlbl);
  });

  host.innerHTML = '';
  host.appendChild(svg);
}

// ─── Apply analytics data to UI ──────────────────────────────────────────────
function applyAnalytics(data) {
  // Stat cards
  document.getElementById('stat-total').textContent = (data.total ?? '–').toLocaleString();
  const open   = (data.by_status['Pending']||0) + (data.by_status['In Progress']||0);
  const closed = (data.by_status['Resolved']||0) + (data.by_status['Closed']||0);
  document.getElementById('stat-open').textContent   = open.toLocaleString();
  document.getElementById('stat-closed').textContent = closed.toLocaleString();

  // Trend pill
  const pill = document.getElementById('trend-pill');
  if (data.trend) {
    const delta = data.trend.delta;
    pill.style.display = 'inline-flex';
    pill.className = 'trend-pill ' + (delta > 0 ? 'up' : delta < 0 ? 'down' : 'flat');
    pill.textContent = `${delta > 0 ? '▲' : delta < 0 ? '▼' : '▬'} ${delta > 0 ? '+' : ''}${delta} vs last month`;
  } else {
    pill.style.display = 'none';
  }

  // Monthly volume bar chart
  svgBarChart(
    'chart-monthly',
    data.monthly_volume.map(m => m.month.slice(-2)), // works for both "25-01" (baseline) and "2025-01" (live API)
    data.monthly_volume.map(m => m.count),
    _currentSource === 'live' ? '#3F8489' : '#3F8489'
  );

  // Category donut
  const catLabels  = Object.keys(data.by_category);
  svgDonutChart('chart-category', catLabels.map((l, i) => ({
    label: l, value: data.by_category[l], color: CATEGORY_COLORS[i % CATEGORY_COLORS.length]
  })));

  // Priority horizontal bar
  const priOrder = ['Low','Medium','High'];
  svgHBarChart(
    'chart-priority',
    priOrder,
    priOrder.map(p => data.by_priority[p] || 0),
    priOrder.map(p => PRIORITY_COLORS[p])
  );

  // Status donut
  const statLabels = Object.keys(data.by_status);
  svgDonutChart('chart-status', statLabels.map(l => ({
    label: l, value: data.by_status[l], color: STATUS_COLORS[l] || '#8695A4'
  })));
}

// ─── Source pill UI ──────────────────────────────────────────────────────────
function setSourcePill(source, liveTotal) {
  const pill = document.getElementById('ds-source-pill');
  if (!pill) return;
  if (source === 'baseline') {
    pill.className = 'ds-source-pill baseline';
    pill.textContent = 'Comcast Baseline · 2,224 complaints';
  } else {
    pill.className = 'ds-source-pill live';
    pill.textContent = `Live Data · ${(liveTotal||0).toLocaleString()} complaints`;
  }
}

// ─── Toggle handler (called from HTML onclick) ───────────────────────────────
function switchDataSource(source) {
  _currentSource = source;
  document.getElementById('btn-baseline').classList.toggle('active', source === 'baseline');
  document.getElementById('btn-live').classList.toggle('active', source === 'live');

  if (source === 'baseline') {
    applyAnalytics(BASELINE);
    setSourcePill('baseline');
  } else {
    if (_liveData) {
      applyAnalytics(_liveData);
      setSourcePill('live', _liveData.total);
    } else {
      // Show loading state in chart hosts
      ['chart-monthly','chart-category','chart-priority','chart-status'].forEach(id => {
        const h = document.getElementById(id);
        if (h) h.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:140px;color:#8695A4;font:13px Inter,sans-serif;gap:8px"><span>Loading live data…</span></div>';
      });
      fetchAndRenderLive();
    }
  }
}

// ─── ML status (unchanged from original) ────────────────────────────────────
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

// ─── Analytics: live fetch + render ─────────────────────────────────────────
async function fetchAndRenderLive() {
  try {
    const data = await adminFetch('/admin/analytics');
    _liveData = data;
    // Only apply if user is still on 'live'
    if (_currentSource === 'live') {
      applyAnalytics(data);
      setSourcePill('live', data.total);
    }
  } catch (e) {
    console.warn('Could not load live analytics:', e);
    if (_currentSource === 'live') {
      adminShowToast('Could not load live analytics. Showing baseline.');
      switchDataSource('baseline');
    }
  }
}

// ─── loadAnalytics: fetch live data, cache it, render baseline on first load ─
async function loadAnalytics() {
  // Always render baseline immediately so charts are never blank
  applyAnalytics(BASELINE);
  setSourcePill('baseline');

  // Fetch live in background; cache it so the toggle is instant
  try {
    const data = await adminFetch('/admin/analytics');
    _liveData = data;
    // If user already toggled to live before fetch finished, apply now
    if (_currentSource === 'live') {
      applyAnalytics(data);
      setSourcePill('live', data.total);
    }
  } catch (e) {
    console.warn('Could not load live analytics (baseline shown):', e);
  }
}

// ─── Categories (unchanged from original) ────────────────────────────────────
async function loadCategoryOptions() {
  let categories = [];
  try {
    categories = await adminFetch('/categories');
  } catch (e) {
    categories = ['Billing','Financial','Technical','Service','Others'];
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

// ─── Table (unchanged from original) ─────────────────────────────────────────
function buildQueryString() {
  const params = new URLSearchParams();
  params.set('page', currentPage);
  params.set('page_size', PAGE_SIZE);
  const category = document.getElementById('filter-category').value;
  const priority  = document.getElementById('filter-priority').value;
  const status    = document.getElementById('filter-status').value;
  const search    = document.getElementById('filter-search').value.trim();
  if (category) params.set('category', category);
  if (priority)  params.set('priority', priority);
  if (status)    params.set('status', status);
  if (search)    params.set('search', search);
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

function statusClassFor(status)   { return ['Resolved','Closed'].includes(status) ? 'resolved' : 'pending'; }
function priorityClassFor(priority) { return (priority||'low').toLowerCase(); }

function renderTable(items) {
  const tbody   = document.getElementById('admin-tbody');
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
            `<option value="${cat}" ${cat===c.category?'selected':''}>${cat}</option>`).join('')}
        </select>
      </td>
      <td>
        <select class="inline-select" data-field="priority" data-ticket="${c.ticket_no}">
          ${['Low','Medium','High'].map(p =>
            `<option value="${p}" ${p===c.priority?'selected':''}>${p}</option>`).join('')}
        </select>
      </td>
      <td class="complaint-text" title="${escapeHtml(c.complaint)}">${escapeHtml(c.complaint)}</td>
      <td>${escapeHtml(c.date_month_year)}</td>
      <td>${escapeHtml(c.city||'—')}</td>
      <td>${escapeHtml(c.received_via)}</td>
      <td>
        <select class="inline-select" data-field="status" data-ticket="${c.ticket_no}">
          ${['Pending','In Progress','Resolved','Closed'].map(s =>
            `<option value="${s}" ${s===c.status?'selected':''}>${s}</option>`).join('')}
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
  const field  = selectEl.dataset.field;
  const value  = selectEl.value;
  selectEl.disabled = true;
  try {
    await adminFetch(`/admin/complaints/${ticket}`, {
      method: 'PATCH',
      body: JSON.stringify({ [field]: value })
    });
    adminShowToast(`Ticket #${ticket} updated.`);
    // Refresh live data cache then re-render whichever source is active
    const freshData = await adminFetch('/admin/analytics').catch(() => null);
    if (freshData) {
      _liveData = freshData;
      if (_currentSource === 'live') applyAnalytics(freshData);
    }
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

// ─── View modal (unchanged from original) ────────────────────────────────────
function openViewModal(ticketNo) {
  const c = lastPageData.items.find(i => i.ticket_no === ticketNo);
  if (!c) return;
  document.getElementById('view-body').innerHTML = `
    <div class="view-grid">
      <div><strong>Ticket #</strong><div>${c.ticket_no}</div></div>
      <div><strong>Status</strong><div><span class="status-badge ${statusClassFor(c.status)}">${escapeHtml(c.status)}</span></div></div>
      <div><strong>Category</strong><div>${escapeHtml(c.category)}</div></div>
      <div><strong>Priority</strong><div><span class="priority-badge ${priorityClassFor(c.priority)}">${escapeHtml(c.priority)}</span></div></div>
      <div><strong>Date</strong><div>${escapeHtml(c.date_month_year)} ${escapeHtml(c.time||'')}</div></div>
      <div><strong>Received via</strong><div>${escapeHtml(c.received_via)}</div></div>
      <div><strong>City</strong><div>${escapeHtml(c.city||'—')}</div></div>
      <div><strong>State</strong><div>${escapeHtml(c.state||'—')}</div></div>
      <div><strong>Zip</strong><div>${escapeHtml(c.zipcode||'—')}</div></div>
      <div><strong>Linked customer</strong><div>${c.user_id?`User #${c.user_id}`:'None (manual entry)'}</div></div>
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

// ─── Manual entry modal (unchanged from original) ────────────────────────────
function openManualModal() {
  document.getElementById('manual-form').reset();
  document.getElementById('manual-modal').classList.add('open');
  document.body.style.overflow = 'hidden';
}
function closeManualModal() {
  document.getElementById('manual-modal').classList.remove('open');
  document.body.style.overflow = '';
}

// ─── Debounce ─────────────────────────────────────────────────────────────────
function debounce(fn, ms) {
  let t;
  return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
}

// ─── DOMContentLoaded (unchanged wiring from original) ───────────────────────
document.addEventListener('DOMContentLoaded', async () => {
  const session = adminGuardAndWireNav();
  if (!session) return;

  await loadCategoryOptions();
  loadMlStatus();
  loadAnalytics();   // renders baseline instantly, fetches live in background
  loadTable();

  document.getElementById('filter-category').addEventListener('change',  () => { currentPage=1; loadTable(); });
  document.getElementById('filter-priority').addEventListener('change',   () => { currentPage=1; loadTable(); });
  document.getElementById('filter-status').addEventListener('change',     () => { currentPage=1; loadTable(); });
  document.getElementById('filter-search').addEventListener('input', debounce(() => { currentPage=1; loadTable(); }, 350));
  document.getElementById('filter-clear').addEventListener('click', () => {
    document.getElementById('filter-category').value = '';
    document.getElementById('filter-priority').value = '';
    document.getElementById('filter-status').value   = '';
    document.getElementById('filter-search').value   = '';
    currentPage = 1; loadTable();
  });

  document.getElementById('page-prev').addEventListener('click', () => { if (currentPage>1) { currentPage--; loadTable(); } });
  document.getElementById('page-next').addEventListener('click', () => {
    const totalPages = Math.max(1, Math.ceil(lastPageData.total / lastPageData.page_size));
    if (currentPage < totalPages) { currentPage++; loadTable(); }
  });

  document.getElementById('view-close').addEventListener('click', closeViewModal);
  document.getElementById('view-close-btn').addEventListener('click', closeViewModal);
  document.getElementById('view-modal').addEventListener('click', e => { if (e.target.id==='view-modal') closeViewModal(); });

  document.getElementById('btn-new-complaint-admin').addEventListener('click', openManualModal);
  document.getElementById('manual-close').addEventListener('click', closeManualModal);
  document.getElementById('manual-cancel').addEventListener('click', closeManualModal);
  document.getElementById('manual-modal').addEventListener('click', e => { if (e.target.id==='manual-modal') closeManualModal(); });

  document.getElementById('manual-form').addEventListener('submit', async e => {
    e.preventDefault();
    const body = {
      complaint:    document.getElementById('m-complaint').value.trim(),
      category:     document.getElementById('m-category').value || null,
      priority:     document.getElementById('m-priority').value || null,
      received_via: document.getElementById('m-received-via').value,
      status:       document.getElementById('m-status').value,
      city:         document.getElementById('m-city').value.trim() || null,
      state:        document.getElementById('m-state').value.trim() || null,
      zipcode:      document.getElementById('m-zip').value.trim() || null,
    };
    if (!body.complaint) { adminShowToast('Please enter a complaint description.'); return; }
    try {
      const created = await adminFetch('/admin/complaints', { method:'POST', body:JSON.stringify(body) });
      adminShowToast(`Complaint #${created.ticket_no} added.`);
      closeManualModal();
      currentPage = 1;
      loadTable();
      // Refresh analytics
      const freshData = await adminFetch('/admin/analytics').catch(()=>null);
      if (freshData) {
        _liveData = freshData;
        if (_currentSource === 'live') applyAnalytics(freshData);
        else applyAnalytics(BASELINE); // keep baseline display but cache live
      }
    } catch (err) {
      adminShowToast(err.message || 'Could not add complaint.');
    }
  });

  document.addEventListener('keydown', e => {
    if (e.key !== 'Escape') return;
    if (document.getElementById('view-modal').classList.contains('open'))   closeViewModal();
    if (document.getElementById('manual-modal').classList.contains('open')) closeManualModal();
  });
});
