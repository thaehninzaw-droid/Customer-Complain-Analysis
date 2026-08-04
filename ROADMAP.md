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
| Admin AI Chatbot (RAG: Gemini + Qdrant) | ✅ Built. Credentials (Gemini key, Qdrant) are ready but ⚠️ not yet tested against the real services |
| Full FastAPI HTTP layer test pass | ✅ Confirmed - CI is green (see `docs/TESTING.md`) |
| Real Kaggle dataset loaded | ✅ Done - `backend/data/comcast_complaints.csv`, both models retrained against it (see `docs/ALGORITHMS.md`) |
| Pushed to a real GitHub remote | ✅ Done - CI running on every push, confirmed green |
| Deployed (Render/Atlas/Qdrant Cloud) | ❌ Not yet - credentials ready, see `docs/DEPLOYMENT.md` for the plan |
| CI (GitHub Actions running tests on push) | ✅ Done and green - `.github/workflows/tests.yml` |
| Real Gemini/Qdrant calls tested | ⚠️ Credentials ready, not yet exercised anywhere (CI deliberately has no API keys configured) |
| Real MongoDB Atlas tested | ⚠️ Connection string ready, not yet exercised anywhere (CI and local dev both still use the in-memory fallback) |
| Demo-mode date shifting for presentations | ✅ Done - `--demo-shift-dates` flag, see `docs/DECISIONS.md` #19 |
| Password show/hide toggle | ✅ Done (small UX addition, `docs/DECISIONS.md` #19) |
| Full dependency set installed + CI reproduced locally | ✅ Done this session - real `fastapi`/`pytest`/`xgboost` etc. installed in an environment with genuine internet access (PyPI only, see below); 83/83 tests pass. See `docs/DECISIONS.md` #20 |
| Shipped priority-model artifacts are real XGBoost | ✅ Resolved this session - retrained locally now that `xgboost` is installed; `backend/app/ml/artifacts/priority_metrics.json` now reads `"model": "XGBClassifier(n_estimators=200, max_depth=4)"`, not the scikit-learn fallback. See `docs/DECISIONS.md` #20 |
| Live end-to-end API smoke test (customer + admin flows) | ✅ New this session - `backend/scripts/manual_api_smoke_check.py`, run against a real local `uvicorn` process. 20/20 checks pass. Still against the **in-memory** DB and template chatbot fallback, not real Mongo/Gemini/Qdrant - see `docs/DECISIONS.md` #20 |
| Real MongoDB Atlas / Gemini / Qdrant / deployment | ❌ Still blocked - **not a missing-credential problem, a network problem**: this session's sandbox can only reach PyPI/npm/GitHub (confirmed via direct test, `x-deny-reason: host_not_allowed` on MongoDB Atlas, the Gemini API, Qdrant Cloud, and Render). See `docs/DECISIONS.md` #20 and the note below. |
| Junior-proposed "activities" feature (`Myactivities.zip`) | ✅ Evaluated - already exists in Loopline, more completely (real ML classification, real status workflow, real auth/data isolation vs. the prototype's plaintext-password/no-isolation/always-"Pending" version). No new feature needed. Two small hardening ideas borrowed and **implemented**: server-side complaint length/city validation, and a `GET /cities` endpoint. See `docs/DECISIONS.md` #21/#22. |
| Junior-friendly step-by-step setup guide | ✅ Done - `docs/GETTING_STARTED.md`, assumes zero prior familiarity (not even that Python is installed). See `docs/DECISIONS.md` #21. |

## A hard constraint discovered this session (read before attempting steps 1-3 below)

This session's environment is network-sandboxed to package registries
and GitHub only (PyPI, npm, GitHub - enough to `pip install` the real
dependency set and reproduce CI locally, which is new progress - see
`docs/DECISIONS.md` #20). It **cannot reach MongoDB Atlas,
generativelanguage.googleapis.com (Gemini), Qdrant Cloud, or Render**
at all, confirmed by direct request (each returns a `403` from the
sandbox's own egress proxy with `x-deny-reason: host_not_allowed`,
before ever reaching the real service). This is true **regardless of
whether real credentials are supplied** - it's a network policy on
this environment, not an auth problem.

Practically: steps 1-3 below (real Atlas, real Gemini+Qdrant, real
deployment) cannot be executed *from inside this session*. They need
either (a) a session/environment with those hosts allow-listed, or (b)
running the equivalent commands yourself, locally, with your own
network access - every command you'd need is already spelled out below
and in `docs/DEPLOYMENT.md`. This is a good fit for Claude Code running
on your own machine, which would have normal internet access. Steps 4
(the honest remainder of local hardening/validation work) are unaffected
and are exactly what this session focused on instead.

## Immediate next steps (in order)

All three credentials (MongoDB Atlas URI, Gemini API key, Qdrant) are
ready as of this handoff, but none has been exercised against the
real service yet. The order below is deliberate, not arbitrary - see
the reasoning under each step, and HANDOFF.md for the full context.

1. **Real MongoDB Atlas first.** This is the foundational data layer
   everything else sits on top of, and it's the lowest-risk of the
   three to validate - set `MONGODB_URI` in `.env`, start the API,
   confirm the demo admin account gets seeded there (check Atlas's
   collections directly), run `python -m data.load_dataset
   data/comcast_complaints.csv` against it, and click through both the
   customer and admin flows to confirm reads/writes persist correctly.
   Validating this first means every later step is testing against a
   real database, not silently still using the in-memory fallback.
2. **Gemini + Qdrant together, second.** They're used together in
   practice (the knowledge-base indexer calls Gemini for embeddings,
   then writes to Qdrant; the chatbot calls Gemini for embeddings and
   generation, then reads from Qdrant) - testing them as a pair
   matches how they're actually exercised. Set `GEMINI_API_KEY` and
   `QDRANT_URL`/`QDRANT_API_KEY`, run
   `python -m app.rag.knowledge_base` to index the SOP docs, then ask
   the Admin AI Chatbot a real question and confirm `used_rag: true`
   comes back instead of the fallback message.
3. **Deploy for real, last - only after 1 and 2 are confirmed working
   locally.** Once the API is known to work correctly against the real
   Atlas cluster and the real Gemini/Qdrant services on your own
   machine, deploying to Render becomes "point the same environment
   variables at the same already-working services," rather than
   debugging three unknowns (is it Render? Atlas? Gemini?) at once in
   a harder-to-iterate-on deployed environment. `docs/DEPLOYMENT.md`
   has the full free-tier walkthrough (Render + Atlas + Qdrant Cloud).
4. **Click through both flows manually, at least once, with your own
   eyes**, ideally against the real (not in-memory) backend from step
   1. Customer: signup → file a complaint → see it in Activities with
   an auto-assigned category. Admin: admin login → dashboard loads
   with real 2015 complaint history in the charts (including the June
   2015 spike - see `docs/ALGORITHMS.md`) → filter/search/paginate the
   table → add a complaint manually → inline-edit a status → AI
   Chatbot page answers a question with a real RAG-backed answer. CI
   proves the API responds correctly; it doesn't prove the pages
   look/feel right, or that a real generated chatbot answer is
   actually good.

## Medium-term (nice to have before the defense)

- ~~If there's internet access anywhere in the pipeline, confirm the
  real XGBoost path works~~ **Confirmed via CI** - see
  `docs/TESTING.md`.
- Resolve the Billing/Financial category overlap (still an open
  question - see `docs/DECISIONS.md`'s "Open questions" section).
- Get the actual thesis rubric and check this against it directly,
  rather than against a best-guess of "needs an algorithm, data
  analysis, and a recommendation."
- Add server-side complaint length + city validation to
  `POST/PATCH /complaints` (currently only enforced client-side in
  `script.js` - a junior-proposed prototype does this server-side and
  it's worth matching; see `docs/DECISIONS.md` #21). ~~Done~~ -
  implemented in `app/validation.py`, see `docs/DECISIONS.md` #22.
- Consider a `GET /cities` endpoint so the Myanmar city list isn't
  only reachable from frontend JS (same source, #21). ~~Done~~ - see
  `app/cities.py` and `docs/DECISIONS.md` #22. **Follow-up still
  open**: `frontend/script.js` doesn't fetch from it yet, still has
  its own (currently identical, but not drift-proof) hardcoded copy.

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
