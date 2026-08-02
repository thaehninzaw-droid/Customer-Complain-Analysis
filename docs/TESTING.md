# Testing status

**Update: CI is green** (`.github/workflows/tests.yml`, running on
GitHub Actions across Python 3.11/3.12) - see the "✅ Confirmed by CI"
section below for exactly what that now proves, and the sections after
it for what's still genuinely unverified (real MongoDB, real
Gemini/Qdrant - CI doesn't have credentials for either, so those code
paths still haven't executed anywhere yet).

The rest of this document describes the situation as it stood while
this backend was originally built: the environment had **no internet
access** and did not have `fastapi`, `pydantic`, `pytest`, `httpx`,
`uvicorn`, `xgboost`, `google-genai`, or `qdrant-client` installed
(confirmed: `pip install` fails outright, not just slowly). It did
have `numpy`, `pandas`, `scikit-learn`, `joblib`, `requests`, and
`pypdf`. That's the context for why the split below exists at all.

## ✅ Confirmed by CI (GitHub Actions, real internet access)

- **The entire FastAPI HTTP layer** - `tests/test_api.py` runs for
  real now: request validation, session-token auth, the admin-role
  check (`get_current_admin_id`), `/admin/complaints` filtering/
  pagination, `PATCH`/`POST` admin endpoints, the
  `@app.on_event("startup")` admin-seeding hook, CORS, all of it. This
  was the single largest unverified surface area before CI existed -
  see the git history if you want the exact diff between "reviewed by
  eye" and "actually running."
- **The real XGBoost training path.** CI installs `requirements.txt`
  (which lists `xgboost` plainly, no longer gated behind "only if you
  have internet") with real internet access, so
  `app/ml/train_priority.py`'s `from xgboost import XGBClassifier`
  branch runs for real, not just the scikit-learn fallback. Check a
  CI run's "Report which priority model actually trained" step - it
  should print `Model used: XGBClassifier(...)`, not
  `HistGradientBoostingClassifier(...)`.
- **Pydantic model validation** for every request/response shape in
  `app/models.py` - previously only checked by reading the code.

## ✅ Actually run and passing, in this environment

Everything with no FastAPI/pydantic dependency was imported and
exercised directly (both via the committed pytest-style test files in
`backend/tests/`, and via extra manual verification while building):

- `app/sentiment.py`, `app/priority.py`, `app/classify.py` - including
  the two real bugs found and fixed (see docs/ALGORITHMS.md) and the
  confidence-gate fix for out-of-vocabulary text.
- `app/ml/train_classifier.py`, `app/ml/train_priority.py`,
  `app/ml/classifier_model.py`, `app/ml/priority_model.py` - actually
  trained against the real Kaggle dataset, real accuracy numbers
  produced (see `app/ml/artifacts/*_metrics.json`), predictions
  spot-checked. (Two more real bugs found this way - numpy scalar
  types leaking into what would become MongoDB documents - see
  docs/ALGORITHMS.md and DECISIONS.md #17.)
- `data/load_dataset.py` - run end-to-end against the real 2224-row
  dataset, including the date/status normalization it turned out to need.
- `app/db.py`'s in-memory fallback, including the new `find_one`/
  `update_one` methods added for the admin edit endpoints.
- `app/analytics.py`, `app/pulse.py`, `app/security.py`,
  `app/sessions.py` - all pure-Python, all tested directly.
- `app/admin_seed.py` - idempotency verified directly.
- `app/rag/knowledge_base.py`'s chunking/loading logic, and
  `app/rag/vector_store.py`'s in-memory cosine-similarity search -
  both tested with fake embedding vectors (no real Gemini calls made).
- All frontend JavaScript (`config.js`, `auth.js`, `script.js`,
  `admin.js`, `admin-dashboard.js`, `admin-chatbot.js`) - syntax-
  checked with `node --check`, and every `getElementById()` call
  cross-referenced against the actual HTML files' `id` attributes to
  catch typos/renames (a real class of bug that's easy to introduce
  during a big rewrite and easy to miss just by reading the code).
- All HTML files - checked for balanced/well-formed tags with Python's
  `html.parser`.
- CSS - checked for balanced braces.

## ⚠️ Still not runtime-executed anywhere

- **The Gemini and Qdrant REST calls themselves**
  (`app/rag/gemini_client.py`, the Qdrant branch of
  `app/rag/vector_store.py`). The request/response shapes were
  verified against live API documentation (see docs/RAG_CHATBOT.md for
  citations), but no actual HTTP call has been made against either
  service - CI doesn't have a `GEMINI_API_KEY`/`QDRANT_URL` secret
  configured (correctly - those should stay out of a student repo's
  CI config unless you deliberately add them as GitHub Secrets), and
  neither did the original build environment.
  **Set `GEMINI_API_KEY` and test `/chatbot/recommend` and
  `/admin/chatbot/ask` end-to-end before demoing the RAG chatbot.**
- **Real MongoDB Atlas.** CI runs with `MONGODB_URI` unset, same as
  local dev - so it exercises the in-memory fallback (`db.py`'s
  `_InMemoryCollection`), not the real-pymongo code path
  (`get_collection()`'s branch when `MONGODB_URI` is set). That
  branch has still never been exercised against an actual MongoDB
  instance anywhere. If you want CI to cover this too, add
  `MONGODB_URI` as a GitHub Actions secret pointing at a real (ideally
  disposable/test) Atlas cluster.

## Before you trust this for a demo or a grade

1. ~~`pip install -r requirements-dev.txt` and run `pytest`~~ **Done -
   CI covers this on every push now.** Still worth running locally
   before pushing, and worth glancing at a CI run's logs at least once
   to see it for yourself rather than taking "green checkmark" alone
   as the full picture.
2. Start the server (`uvicorn app.main:app --reload`) and click
   through both the customer flow (signup → file a complaint → see it
   in Activities) and the admin flow (admin login → dashboard loads →
   filters/pagination work → manually add a complaint → inline-edit a
   status) at least once. CI proves the HTTP layer *responds
   correctly*; it doesn't prove the pages *look* right or that the
   charts render sensibly - that still needs a human looking at it.
3. If demoing the RAG chatbot, set `GEMINI_API_KEY`, run
   `python -m app.rag.knowledge_base`, and ask it a real question
   before relying on it live - confirm `used_rag: true` comes back,
   not the fallback message.
4. ~~If you have internet access and want the real XGBoost path~~ **CI
   already confirms this** - check a CI run's "Report which priority
   model actually trained" step output.
5. If you want CI to also cover the real-MongoDB code path, add
   `MONGODB_URI` as a GitHub Actions secret (Settings → Secrets and
   variables → Actions) pointing at a real cluster, then reference it
   in `.github/workflows/tests.yml`'s `env:` for the test step. Not
   done yet - see the section above.

None of the above changes any code - it's confirming that code already
written and reviewed actually behaves as intended once it can run in a
normal environment.
