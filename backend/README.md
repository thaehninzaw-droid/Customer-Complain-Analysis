# Loopline Backend

A FastAPI backend for the complaint classification system - matches
the frontend's existing field names/endpoints, runs with **zero setup**
using in-memory fallbacks for both the database and the vector store,
and upgrades to the real thing (MongoDB Atlas, Qdrant, Gemini) purely
by setting environment variables - no code changes needed either way.

See `../docs/` for the full documentation set (architecture, the two
ML algorithms, the RAG chatbot, admin auth, deployment) and
`../ROADMAP.md` for what's done vs. still ahead.

## Quickstart

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements-dev.txt

# trains the real ML models (Algorithm 1 + Algorithm 2) against the
# real dataset already included at data/comcast_complaints.csv; skip
# this and everything still works via the rule-based baselines instead
python -m app.ml.train_classifier
python -m app.ml.train_priority

uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000/docs for interactive API docs.

A demo admin account is seeded automatically on startup - check the
console output for the email/password (defaults: `admin@loopline.io` /
`ChangeMe123!`, override via `.env` - see `.env.example`).

## What's built

### Customer-facing
- `POST /auth/signup`, `POST /auth/login` - passwords hashed
  server-side (PBKDF2), session tokens returned for `Authorization:
  Bearer <token>` on everything else.
- `POST /complaints` - auto-classified (**Algorithm 1**) and
  auto-prioritized (**Algorithm 2**) unless the client overrides
  either. `user_id` comes from the session token, never the request
  body (fixes a real IDOR vulnerability - see DECISIONS.md #9).
- `GET /complaints` - the caller's own complaints only.
- `GET /dashboard-stats`, `GET /issues/pulse`, `GET /categories` -
  public aggregate/reference endpoints.
- `POST /chatbot/recommend` - category + a recommended action, backed
  by the real RAG pipeline if `GEMINI_API_KEY` is set, a template
  otherwise (see docs/RAG_CHATBOT.md).

### Admin (all require `Authorization: Bearer <admin token>`)
- `GET /admin/complaints` - paginated, filterable (category/status/
  priority), searchable (ticket # or text).
- `POST /admin/complaints` - manual entry (phone-in complaints, etc.).
- `PATCH /admin/complaints/{ticket_no}` - inline edit (status/
  category/priority).
- `GET /admin/analytics` - monthly volume, category/status/priority
  distribution, month-over-month trend.
- `GET /admin/ml-status` - whether the trained models are loaded, plus
  their last training-run metrics.
- `POST /admin/chatbot/ask` - free-form Q&A grounded in the indexed
  SOP knowledge base (the Admin AI Chatbot module).

Full request/response shapes: `docs/API_REFERENCE.md`, or just visit
`/docs` once the server's running.

## The two algorithms

- **Algorithm 1 (category classification)**: `app/classify.py` ->
  TF-IDF + Logistic Regression (`app/ml/train_classifier.py`), falls
  back to a keyword baseline if no trained model exists yet.
- **Algorithm 2 (priority prediction)**: `app/priority.py` ->
  sentiment/urgency features + a boosted-tree model (XGBoost if
  installed, scikit-learn's HistGradientBoostingClassifier otherwise -
  `app/ml/train_priority.py`), falls back to a rule-based heuristic.

Both training labels come from **distant/weak supervision** (the
existing rule-based baselines bootstrap the labels the ML models
train on) - see `docs/ALGORITHMS.md` for the full methodology
writeup, which is worth citing directly in the thesis.

Train (or retrain) either model:
```bash
python -m app.ml.train_classifier   # writes app/ml/artifacts/category_*
python -m app.ml.train_priority     # writes app/ml/artifacts/priority_*
```

## The dataset

**The real dataset is loaded**: `data/comcast_complaints.csv` (2224
rows, from Kaggle's "Comcast Telecom Complaints" dataset). Both
training scripts use it automatically (they check for this exact
filename first) - the numbers in `app/ml/artifacts/*_metrics.json` are
real, not synthetic. See `docs/ALGORITHMS.md` for the actual accuracy
numbers, a few real bugs the real data surfaced (date format, status
vocabulary, a monthly-volume windowing bug, numpy type leakage into
MongoDB documents), and a genuinely interesting finding in the data
itself.

`data/generate_synthetic_dataset.py` still exists and still works - a
synthetic stand-in kept for anyone who wants to regenerate/extend test
data without touching the real dataset, or reproduce the pipeline from
scratch. `data/sample_complaints.csv` (5 rows) is an even smaller
smoke-test fixture.

Reload the real data or point at a different CSV:
```bash
python -m data.load_dataset data/comcast_complaints.csv
```

## The RAG chatbot (Gemini + Qdrant)

See `docs/RAG_CHATBOT.md` for the full architecture. Short version:
set `GEMINI_API_KEY` in `.env`, then index the SOP knowledge base:
```bash
python -m app.rag.knowledge_base
```
`QDRANT_URL` is optional - leave it unset to use an in-memory
brute-force vector search fallback (fine for this KB's size).
Everything works with neither set too, just with template-based
answers instead of real generated ones.

## Admin accounts

There's no public admin signup - matches the SRS ("Admin Login <log
in only>"). The demo account is auto-seeded on every API startup (see
`app/admin_seed.py`). Once real MongoDB is set up, run
`python -m data.seed_admin` once against it too (the auto-seed on
startup only touches whichever DB that process instance is using).

## Run the tests

```bash
pytest
```
Also runs automatically on every push/PR via GitHub Actions once this
is pushed to GitHub - see `../.github/workflows/tests.yml`.

See `docs/TESTING.md` for exactly what's been runtime-verified vs.
what's only been reviewed/syntax-checked (the environment this backend
was built in has no internet access and doesn't have `fastapi`,
`pydantic`, or `pytest` installed - see that doc for the details and
what to check first when you do have them installed).

## Deploying (free-tier plan)

- **API**: Render (free web service tier)
- **Database**: MongoDB Atlas M0 (free forever, 512 MB)
- **Vector store**: Qdrant Cloud free tier, or skip it and use the
  in-memory fallback for a small KB like this one
- **LLM**: Gemini API (pay-as-you-go, generous free quota)

See `docs/DEPLOYMENT.md` for the full walkthrough.
