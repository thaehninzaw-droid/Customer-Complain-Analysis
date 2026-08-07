# Roadmap

Living document - update this whenever a milestone lands or the plan
changes. See `docs/DECISIONS.md` for the *why* behind each of these;
this file is just the *what* and *what's next*.

## Status at a glance

| Area | Status |
|---|---|
| Customer signup/login/complaint filing | ✅ Done, real backend |
| Algorithm 1 - category classification | ✅ Done, trained model + baseline fallback |
| Algorithm 2 - priority prediction | ✅ Done, trained model + baseline fallback |
| Admin auth (roles, secured endpoints) | ✅ Done |
| Admin dashboard (table, filters, charts, manual entry, inline edit) | ✅ Done |
| Admin AI Chatbot (RAG: Gemini + Qdrant) | ✅ Built and **confirmed working on real Gemini + Qdrant** (tested locally by the team — AI Chatbot returns real RAG-backed answers). |
| Full FastAPI HTTP layer test pass | ✅ Confirmed - CI is green (see `docs/TESTING.md`) |
| Real Kaggle dataset loaded | ✅ Done - `backend/data/comcast_complaints.csv`, both models retrained against it (see `docs/ALGORITHMS.md`) |
| Pushed to a real GitHub remote | ✅ Done - CI running on every push, confirmed green |
| Deployed (Render/Atlas/Qdrant Cloud) | ❌ Not yet - credentials ready, see `docs/DEPLOYMENT.md` for the plan |
| CI (GitHub Actions running tests on push) | ✅ Done and green - `.github/workflows/tests.yml` |
| Real Gemini/Qdrant calls tested | ✅ **Confirmed working** - tested locally by the team. Knowledge base indexed, chatbot returns real answers with `used_rag: true`. CI still has no API keys (intentional). |
| Real MongoDB Atlas tested | ⚠️ Connection string ready, not yet exercised anywhere (CI and local dev both still use the in-memory fallback) |
| Demo-mode date shifting for presentations | ✅ Done - `--demo-shift-dates` flag, see `docs/DECISIONS.md` #19 |
| Password show/hide toggle | ✅ Done (small UX addition, `docs/DECISIONS.md` #19) |
| Full dependency set installed + CI reproduced locally | ✅ Done this session - real `fastapi`/`pytest`/`xgboost` etc. installed in an environment with genuine internet access (PyPI only, see below); 83/83 tests pass. See `docs/DECISIONS.md` #20 |
| Shipped priority-model artifacts are real XGBoost | ✅ Resolved this session - retrained locally now that `xgboost` is installed; `backend/app/ml/artifacts/priority_metrics.json` now reads `"model": "XGBClassifier(n_estimators=200, max_depth=4)"`, not the scikit-learn fallback. See `docs/DECISIONS.md` #20 |
| Live end-to-end API smoke test (customer + admin flows) | ✅ New this session - `backend/scripts/manual_api_smoke_check.py`, run against a real local `uvicorn` process. 20/20 checks pass. Still against the **in-memory** DB and template chatbot fallback, not real Mongo/Gemini/Qdrant - see `docs/DECISIONS.md` #20 |
| Real MongoDB Atlas / Gemini / Qdrant / deployment | ❌ Still blocked - **not a missing-credential problem, a network problem**: this session's sandbox can only reach PyPI/npm/GitHub (confirmed via direct test, `x-deny-reason: host_not_allowed` on MongoDB Atlas, the Gemini API, Qdrant Cloud, and Render). See `docs/DECISIONS.md` #20 and the note below. |
| Junior-proposed "activities" feature (`Myactivities.zip`) | ✅ Evaluated - already exists in Loopline, more completely (real ML classification, real status workflow, real auth/data isolation vs. the prototype's plaintext-password/no-isolation/always-"Pending" version). No new feature needed. Two small hardening ideas borrowed and **implemented**: server-side complaint length/city validation, and a `GET /cities` endpoint. See `docs/DECISIONS.md` #21/#22. |
| Junior-friendly step-by-step setup guide | ✅ Done - `docs/GETTING_STARTED.md`, assumes zero prior familiarity (not even that Python is installed). See `docs/DECISIONS.md` #21. |
| Ticket numbers "only showing 1, 2, 3" | ✅ Investigated - not a real numbering bug (confirmed `app/tickets.py` + both complaint-creation endpoints correctly start at 100001). Root cause was a missing `min` attribute on the admin chatbot's ticket-number input. Fixed. See `docs/DECISIONS.md` #24. |
| Which dataset trains the ML models | ✅ Clarified - `comcast_complaints.csv` (real Kaggle data), confirmed via the training scripts' own fallback order + saved metrics. `synthetic_complaints.csv` is an unused dev-only stand-in. See `docs/DECISIONS.md` #24. |
| Gemini `embedContent` 400 error | ✅ **Fixed and verified** - the `"model"` field fix resolved the issue; RAG confirmed working end-to-end on real hardware. See `docs/DECISIONS.MD` #24. |
| RAG `knowledge_base.py` doesn't pick up `.env` when run standalone | ✅ Fixed - added `load_dotenv()` at top of `knowledge_base.py` with path search for `backend/.env`. See `docs/DECISIONS.md` #26. |
| Qdrant "Collection doesn't exist" unhelpful error | ✅ Fixed - `vector_store.py` now catches the 404 specifically and returns an actionable message pointing to Step 11 of `docs/GETTING_STARTED.md`. |
| Dashboard empty on first startup (in-memory DB) | ✅ Fixed - `app/dataset_seed.py` auto-seeds 2224 complaints from CSV on startup (in-memory mode only). Dashboard shows real data immediately. See `docs/DECISIONS.md` #26. |
| Time picker showing seconds and fractional time | ✅ Fixed - removed seconds dropdown, merged date+time into one row, added clear label "When did this issue occur? Auto-set to now." |
| `docs/VISUALIZATIONS.md` for junior team | ✅ Done - documents all 4 charts + 3 KPI cards + algorithm status chips with data sources, colors, and how to get data showing. |
| Step 11 in GETTING_STARTED.md (RAG indexing) | ✅ Done - full step-by-step for enabling the AI chatbot with real API keys. |
| Analytics dashboard visual polish | ✅ Done - Chart.js replaced with pure SVG (`svgBarChart`, `svgDonutChart`, `svgHBarChart`). Baseline/live toggle. No CDN dependency. See `docs/DECISIONS.md` #27. |
| Switch to Comcast_Cleaned.csv (2025 dates, Complaint_Clean col) | ✅ Done - `backend/data/comcast_complaints.csv` replaced with the cleaned version (same 2224 rows, ISO dates, extra `Complaint_Clean` column). Both models retrained: 93.0%/100% accuracy unchanged. 103/103 tests passing. See `docs/DECISIONS.md` #25. |
| RAG architecture clarified for junior team | ✅ Documented - RAG uses `data/knowledge_base/` SOP docs (Markdown or PDF), not the training datasets. The two datasets train the ML models only. See `docs/DECISIONS.md` #25 and `docs/RAG_CHATBOT.md`. |

## What's confirmed working (as of last local test)

Everything below was confirmed on real infrastructure by the team,
not just in sandboxes:

- ✅ FastAPI backend — customer + admin flows end-to-end
- ✅ Algorithm 1 (category classifier, 93.0% accuracy)
- ✅ Algorithm 2 (priority predictor, 100% vs baseline)
- ✅ RAG chatbot — Gemini + Qdrant, real knowledge-base answers
- ✅ Admin dashboard charts (SVG, no CDN dependency)
- ✅ CI green on every push (GitHub Actions)

## What's still open

**1. Real MongoDB Atlas** — the backend still runs against the
in-memory fallback locally. Switching is one line in `.env`:
```
MONGODB_URI=mongodb+srv://...your Atlas connection string...
```
Then restart `uvicorn`. The admin seed and complaint-filing all work
against the real DB — the code has been ready since Decision 7.
Run `python -m data.load_dataset backend/data/comcast_complaints.csv`
once to populate Atlas with the full 2,224-row history.

**2. Deployment** — never done. All services (Render, Atlas, Qdrant
Cloud) have free tiers. Once MongoDB Atlas is confirmed working
locally (step 1 above), deployment is "point the same env vars at
the same already-working services." Full walkthrough in
`docs/DEPLOYMENT.md`.

**3. Thesis checklist** — before the defense:
- [ ] Get the actual rubric and verify every criterion is covered
  (Algorithms ✅, dataset analysis ✅, recommendation/analytics ✅)
- [ ] Record or run a live demo (customer flow + admin flow + chatbot)
- [ ] One-line mention of known gaps in the write-up ("aware of, out
  of scope") — session tokens, no rate limiting, CORS open, no
  password reset — see "Known gaps" section below

**4. Minor follow-up (low priority, not blocking anything):**
- `frontend/script.js` city list — still hardcoded, doesn't fetch
  from `GET /cities` yet. Both are identical today so no drift, but
  worth cleaning up if touching that file anyway (see
  `docs/FRONTEND_INTEGRATION.md`'s "Cities" section).
- Billing/Financial category overlap — still an open academic
  question (see `docs/DECISIONS.md`'s "Not done yet" section).


## Medium-term (nice to have before the defense)

- ~~If there's internet access anywhere in the pipeline, confirm the
  real XGBoost path works~~ ✅ Confirmed.
- ~~Real Gemini + Qdrant calls tested~~ ✅ Confirmed working locally.
- Resolve the Billing/Financial category overlap (open academic
  question - see `docs/DECISIONS.md`'s "Not done yet" section).
- Get the actual thesis rubric and verify every criterion is met.
- ~~Server-side complaint validation~~ ✅ Done (`app/validation.py`).
- ~~`GET /cities` endpoint~~ ✅ Done (`app/cities.py`). Minor
  follow-up: `script.js` still uses its own hardcoded copy.

## Known gaps, called out on purpose (not oversights)

See `docs/DECISIONS.md`'s "Not done yet" section and
`docs/ADMIN_AUTH.md`'s "what's still not built" section for the full,
honest list - session tokens that never expire, no password reset
flow, no admin permission levels or audit log, no rate
limiting/logging/monitoring, CORS wide open for development. None of
these are hidden; all of them are reasonable "not yet" items for a
project at this stage, and worth a one-line mention in the thesis
itself as "aware of, out of scope" rather than pretending they don't
exist.

## Confirmed decisions (so the next session doesn't need to re-ask)

- **Frontend stays plain HTML/CSS/JS** - no React migration. Decided
  after weighing it explicitly: everything currently works and is
  tested end-to-end; a migration would mean re-verifying all of it for
  a UI that doesn't have the kind of complex shared state where a
  component framework earns its cost. Revisit only if a specific
  external requirement shows up (rubric, portfolio/career goal) that
  didn't exist at decision time.

## Document map

- `HANDOFF.md` - **start here** if picking this project up fresh -
  full system design, standards this project holds itself to, and
  exactly where to resume
- `docs/ARCHITECTURE.md` - system overview, why it's shaped this way
- `docs/ALGORITHMS.md` - both ML algorithms, methodology, bugs found & fixed
- `docs/RAG_CHATBOT.md` - Gemini + Qdrant setup and architecture
- `docs/ADMIN_AUTH.md` - roles, security model, admin account creation
- `docs/API_REFERENCE.md` - every endpoint, request/response shapes
- `docs/TESTING.md` - what's verified vs. reviewed-but-not-run, and why
- `docs/DEPLOYMENT.md` - free-tier deployment walkthrough
- `docs/FRONTEND_INTEGRATION.md` - what changed on the frontend and why
- `docs/DECISIONS.md` - the full ADR log, every major choice explained
- `docs/GIT_SETUP.md` - getting the team onto one shared GitHub repo
