# Dashboard Visualizations

> **Junior team note (Khin Sis Thway's question translated):**
> "What charts and graphs are shown for visualization? Right now there's
> no data so we can't see them."
>
> The charts are auto-populated from the Comcast dataset CSV the moment
> you start the server — no extra step needed in local/development mode.
> If you're using a real MongoDB (`MONGODB_URI` configured), run
> `python -m data.load_dataset backend/data/comcast_complaints.csv`
> once after setup. See `docs/GETTING_STARTED.md` Step 6 and Step 11.

---

## Where the visualizations live

All charts are on the **Admin Dashboard** (`frontend/admin-dashboard.html`),
accessible after logging in as admin. The customer-facing pages have
only their own complaints — no analytics.

---

## Summary KPI cards (top of page)

Three stat tiles showing key numbers at a glance:

| Card | What it shows | Color coding |
|---|---|---|
| **Total Complaints** | All-time total in the database | Neutral |
| **Pending / In Progress** | Active complaints not yet resolved | Amber — draws attention |
| **Resolved / Closed** | Completed complaints | Teal — positive signal |

The **Monthly Volume** chart title also shows a **trend pill** — a small
badge like `▲ +12 vs last month` or `▼ -8 vs last month` — in amber
(rising) or teal (falling). Rising complaints is a warning signal;
falling means things are improving.

---

## Chart 1 — Monthly Volume (bar chart)

**What it shows:** Number of complaints filed each month, up to the
last 24 months of the dataset's own date range.

**Why this is useful:** Shows seasonality, sudden spikes, and whether
complaint volume is trending up or down over time. The busiest month
is highlighted in the trend pill above the chart.

**Technical note:** The window is based on the *dataset's own date
range*, not today's date — so the chart always shows real data even
if the dataset is from a previous year. (Using today's date would make
historical datasets show 12 empty bars, which is useless.)

**Data source:** `date_month_year` field on every complaint → grouped
by YYYY-MM → count per month.

---

## Chart 2 — Category Distribution (doughnut chart)

**What it shows:** Breakdown of complaints by category (Billing,
Technical, Service, Financial, Others), as a percentage of total.

**Center of doughnut:** Total complaint count — a "signature touch" so
the most important number is always readable without hovering.

**Why this is useful:** Tells you which category dominates (usually
Billing or Technical for telecom services) so support teams can staff
and train accordingly. If "Others" is large, it may mean the
auto-categorizer is struggling or new issue types are emerging.

**Data source:** `category` field, assigned by **Algorithm 1**
(TF-IDF + Logistic Regression classifier — see `docs/ALGORITHMS.md`).

**Colors:**
- Billing → Teal `#3F8489`
- Financial → Amber `#FFC94A`
- Technical → Red `#D64545`
- Service → Slate `#8695A4`
- Others → Dark teal `#2C5F63`

---

## Chart 3 — Priority Breakdown (horizontal bar chart)

**What it shows:** How many complaints fall into Low, Medium, and High
priority — displayed as a horizontal bar for easy reading of three
distinct counts.

**Why this is useful:** A large "High" bar means the team is under
pressure and needs to escalate faster. The distribution also validates
**Algorithm 2** — in a healthy dataset, Low should dominate (most
complaints are routine), with Medium and High being progressively
smaller.

**Data source:** `priority` field, assigned by **Algorithm 2**
(XGBoost classifier — see `docs/ALGORITHMS.md`). The distribution from
the Comcast training data is approximately **Low: 80%, Medium: 16%,
High: 4%**.

**Colors:**
- Low → Dark teal `#2C5F63` (calm)
- Medium → Amber `#FFC94A` (caution)
- High → Red `#D64545` (urgent)

---

## Chart 4 — Status Breakdown (doughnut chart)

**What it shows:** Current status of all complaints — Pending, In
Progress, Resolved, Closed — as a proportion of total.

**Center of doughnut:** Total complaint count (same as Category
doughnut).

**Why this is useful:** The ratio of Pending to Resolved tells you how
well the team is keeping up with incoming volume. A large Pending
slice is an operations warning. A large Closed/Resolved slice means
the team is clearing the backlog.

**Data source:** `status` field — set to `Pending` when a complaint
is filed, updated by admin via the inline-edit in the complaints table.
The Comcast dataset's raw values (`Solved`, `Open`, `Closed`,
`Pending`) are mapped to Loopline's vocabulary on load.

**Colors:**
- Pending → Amber `#FFC94A`
- In Progress → Teal `#3F8489`
- Resolved → Dark teal `#2C5F63`
- Closed → Slate `#8695A4`

---

## Algorithm status chips (below the KPI cards)

Two chips at the top of the dashboard show whether the ML models are
loaded:

- **Algorithm 1 — Category classifier**: TF-IDF vectorizer +
  Logistic Regression. Shows accuracy (93.0% vs keyword-baseline
  labels) and whether the model file is loaded.
- **Algorithm 2 — Priority predictor**: XGBoost classifier. Shows
  accuracy (100% vs heuristic baseline labels) and model status.

These chips also appear on the customer-facing homepage for
transparency. If they show "Not loaded," re-run the training scripts:
```
python -m app.ml.train_classifier
python -m app.ml.train_priority
```

---

## Chart rendering library

Charts are rendered in **pure SVG** — no external library, no CDN.
The functions `svgBarChart()`, `svgDonutChart()`, and `svgHBarChart()`
in `frontend/admin-dashboard.js` use the DOM's native SVG API
(`createElementNS`). This works on `file://`, `localhost`, and any
server, and cannot fail due to CDN access issues.

Each chart element is interactive: hovering any bar or donut slice
shows a tooltip with the exact value and percentage.

## Data source toggle

A toggle bar above the charts lets you switch between two data sources:

- **📊 Comcast Baseline (2,224):** The full Comcast dataset statistics
  are hardcoded in the `BASELINE` constant in `admin-dashboard.js`.
  This renders instantly on page load with no network call.
- **🔴 Live Data:** Fetches real-time counts from `GET /admin/analytics`
  (all complaints currently in the database, filed through the app).

On first load, the baseline always renders so charts are never blank.
Live data is fetched in the background and cached — switching to it is
instant once the fetch completes. If the live fetch fails, it falls
back to baseline automatically.

---

## The data behind the charts

In **local/development mode** (no `MONGODB_URI`): the server
auto-seeds the in-memory database from `backend/data/
comcast_complaints.csv` on startup. You'll see the print line:
```
[dataset_seed] Seeded 2224 complaints — dashboard analytics are now populated.
```
in your `uvicorn` terminal, and the charts will render real data
immediately.

In **production mode** (real MongoDB configured): seed the data once
with `python -m data.load_dataset backend/data/comcast_complaints.csv`,
then new complaints filed through the UI add to those numbers in real
time.

---

## Printed analytics (thesis/presentation use)

For a thesis or presentation, the most presentation-ready numbers from
the Comcast dataset (2224 complaints, 2025 date range) are:

| Metric | Value |
|---|---|
| Total complaints | 2,224 |
| Most common category | Billing (~37%) |
| Second most common | Technical (~31%) |
| High priority | ~4% (86 complaints) |
| Resolved/Closed | ~77% |
| Peak month | Varies by date range in dataset |

These are approximations based on how Algorithm 1 and Algorithm 2
classify the data — exact numbers appear live in the dashboard once
the server is running with data seeded.
