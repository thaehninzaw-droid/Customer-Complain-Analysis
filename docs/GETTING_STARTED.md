# Getting started (for anyone new to Loopline)

This doc assumes nothing — not that you have used FastAPI before, not
that you know what a virtual environment is, not that you have touched
this codebase. If you get stuck and the fix is not obvious, that is a
gap in this doc — ask, and the answer should be added to the
Troubleshooting section for the next person.

## What this project actually does

A customer types a banking complaint into a web page ("my credit card
was charged twice", "my account has been frozen without notice"). The
backend automatically figures out *what kind* of complaint it is
(Cards, Accounts, Loans, Collections & Credit reporting, or Other
banking) using Algorithm 1, and *how urgent* it is (Low / Medium /
High) using Algorithm 2. The customer sees their complaint's status
and priority — but never the category (category is admin-only).

A business rule (Decision 34) applies on top of the model: if the
same user files a substantially similar complaint twice in the same
calendar day, priority is forced to High.

An admin has a dashboard to see everything, filter/search, edit
complaints by hand, view analytics, and ask a chatbot questions
grounded in five banking SOP documents (Cards, Accounts, Loans,
Collections, Other banking). The chatbot is not trained on complaint
data — it reads the SOP files only.

---

## Step 1: What you need installed

| Tool | Why | Check |
|---|---|---|
| **Python 3.11 or 3.12** | Runs the backend | `python3 --version` |
| **git** | Version control | `git --version` |
| **A code editor** | VS Code is the common choice | — |
| **A modern browser** | Runs the frontend | — |

You do **not** need Node.js, Docker, MongoDB, or any API keys to get
a fully working version running locally — see Step 5.

**Don't have Python?**
- Windows: download from [python.org/downloads](https://www.python.org/downloads/), tick **"Add python.exe to PATH"** on the first screen.
- Mac: `brew install python@3.12` or download from python.org.
- Linux: `sudo apt install python3 python3-venv`

---

## Step 2: Get the code

**From a zip file** (most likely for this project):
```bash
unzip Loopline_Banking_v*.zip -d loopline
cd loopline/Customer-Complain-Analysis-main
```

**From git:**
```bash
git clone https://github.com/<your-team>/loopline.git
cd loopline
```

Confirm you are in the right place — you should see `backend`,
`frontend`, and `docs`:
```bash
ls
```

---

## Step 3: Set up the backend

Everything in this step runs from inside `backend/`:
```bash
cd backend
```

### 3a. Create a virtual environment
```bash
python3 -m venv venv
```
(Windows: `python -m venv venv`)

### 3b. Activate it — every time you open a new terminal

- Mac/Linux: `source venv/bin/activate`
- Windows PowerShell: `venv\Scripts\Activate.ps1`
- Windows Command Prompt: `venv\Scripts\activate.bat`

Your prompt should now start with `(venv)`. If it does not, the venv
is not active and `import fastapi` will fail.

**Windows "running scripts is disabled" error?**
```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

### 3c. Install dependencies
```bash
pip install -r requirements-dev.txt
```
Takes a minute or two. Works if the last line says
`Successfully installed ...` with no red error above it.

---

## Step 4: Set up your `.env` file

```bash
cp .env.example .env
```
(Windows: `copy .env.example .env`)

**You can leave every value as-is for local development.** The app
runs with no configuration, using an in-memory database and fallback
rule-based logic for anything that would need MongoDB, Gemini, or
Qdrant credentials. See `.env.example` comments for what each
variable controls.

`.env` is already in `.gitignore` — never commit it once it has real
credentials.

---

## Step 5: Prepare the banking dataset and train the models

**This step is required before the app will have real data or real
ML predictions.** Without it the app starts but the database is empty
and classification uses keyword fallbacks only.

### 5a. Download the raw dataset (one-time)

Download the CFPB Consumer Complaints CSV from Kaggle:
```
https://www.kaggle.com/datasets/sebastienverpile/consumercomplaintsdata
```
Place the downloaded file at:
```
backend/data/raw/consumer_complaints.csv
```
(The `raw/` folder already exists. The file is ~400 MB. Do not commit
it to git — it is in `.gitignore`.)

### 5b. Run the cleaning script

```bash
python -m data.clean_banking_dataset
```

This reads the raw file, applies the full cleaning pipeline documented
in `backend/data/EDA.md`, and writes:
```
backend/data/banking_complaints.csv   ← 12,000 clean banking complaints
```
The raw file is never modified. Output is deterministic (seed 42).

Full EDA report: `backend/data/EDA.md`.

### 5c. Train Algorithm 1 (category classifier)

```bash
python -m app.ml.train_classifier
```

Trains TF-IDF + Logistic Regression on the 5 banking categories
using the official CFPB-mapped labels in `banking_complaints.csv`.
Prints accuracy when done (expect ~86% on banking data).

Writes to `backend/app/ml/artifacts/`:
- `category_model.joblib`
- `category_vectorizer.joblib`
- `category_metrics.json`

### 5d. Train Algorithm 2 (priority predictor)

```bash
python -m app.ml.train_priority
```

Trains XGBoost (or HistGradientBoostingClassifier if xgboost is not
installed) over sentiment/urgency features. Labels are generated by
the rule-based baseline (distant supervision — CFPB has no priority
column). Prints the label distribution and accuracy.

Writes to `backend/app/ml/artifacts/`:
- `priority_model.joblib`
- `priority_vectorizer.joblib`
- `priority_label_encoder.joblib`
- `priority_metrics.json`

**Can I skip this?** Yes — the app falls back to keyword-based
classification and rule-based priority automatically if no model
artifacts exist. But the trained models are noticeably better and
only take a few seconds each to train.

---

## Step 6: Run the backend

Still inside `backend/`, with `(venv)` active:
```bash
uvicorn app.main:app --reload
```

You should see:
```
[loopline] Seeded demo admin → email: admin@loopline.io | password: ChangeMe123!
[dataset_seed] Seeding complaints from banking_complaints.csv ...
[dataset_seed] Seeded 12000 banking complaints — dashboard analytics are now populated.
INFO:     Uvicorn running on http://127.0.0.1:8000
```

The admin credentials are seeded automatically every time — no
manual setup. The complaint seeding runs once (skipped if the
collection already has data).

**Confirm it works:** open
[http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs) — you should
see the interactive Swagger UI listing every endpoint.

`--reload` means the server auto-restarts on file changes. Leave this
terminal open while you work.

**"Address already in use"?** Something is already on port 8000.
Run on a different port:
```bash
uvicorn app.main:app --reload --port 8001
```
Then update `API_BASE` in `frontend/config.js` to match.

---

## Step 7: Run the frontend

The frontend is plain HTML/CSS/JavaScript — no build step, no
`npm install`. With the backend running, open `frontend/index.html`
in your browser (double-click it, or drag it into an open browser
window).

**Try it out:**
1. Click "Sign Up" — create a customer account. Password needs 8+
   characters, one uppercase letter, and one of `! @ # $ % ^ & *`
   (e.g. `Passw0rd!`).
2. File a banking complaint — describe a realistic banking problem in
   at least 20 characters. The form only collects:
   - Complaint text
   - Date and time
   - City / region
   There is no category field — category is detected automatically
   server-side by Algorithm 1.
3. Your complaint history shows Ticket #, Complaint text, Date,
   Priority (Low / Medium / High), and Status. Category is not shown
   to the customer.
4. Log out → open `admin-login.html` → log in with the admin
   email/password from the backend terminal.
5. Admin dashboard shows all 5 banking categories, priority
   distribution, monthly volume, and an analytics tab. The chatbot
   tab shows "Chatbot" and answers questions about banking SOP
   procedures.

**Nothing happens / browser console errors?** Open DevTools (F12 →
Console). "Failed to fetch" means the backend is not running or is on
the wrong port.

---

## Step 8: Run the tests

```bash
pytest
```

All 164 tests should pass. Tests cover both algorithms, the same-day
repeat-priority rule, banking category names, SOP file set, BM25
index, API endpoints, and the admin dashboard. The exact count may
grow as more tests are added — what matters is `0 failed`.

To run a specific file:
```bash
pytest tests/test_classify.py -v
pytest tests/test_priority.py -v
pytest tests/test_api.py -v
```

---

## Step 9: Find your way around the codebase

| "I want to change..." | Look here |
|---|---|
| What happens when a complaint is filed | `backend/app/main.py` → `POST /complaints` |
| Same-day repeat → High priority rule | `backend/app/main.py` → `_is_repeat_same_day()` |
| Category classification (Algorithm 1) | `backend/app/classify.py`, `backend/app/ml/train_classifier.py` |
| Priority prediction (Algorithm 2) | `backend/app/priority.py`, `backend/app/ml/train_priority.py` |
| Sentiment / urgency scoring | `backend/app/sentiment.py` |
| The 5 banking categories | `backend/app/categories.py` |
| Chatbot recommendation text | `backend/app/chatbot.py` → `RECOMMENDATIONS` dict |
| Banking SOP documents (chatbot knowledge base) | `backend/data/knowledge_base/*.md` |
| Rebuild BM25 index after editing SOPs | `python -m app.rag.knowledge_base` |
| Dataset cleaning pipeline | `backend/data/clean_banking_dataset.py` |
| EDA report | `backend/data/EDA.md` |
| Myanmar cities (autofills state/zip in the form) | `backend/app/cities.py` |
| Server-side validation (text length, city check) | `backend/app/validation.py` |
| Customer-facing complaint form | `frontend/activities.html` + `frontend/script.js` |
| Admin dashboard | `frontend/admin-dashboard.html` + `frontend/admin-dashboard.js` |
| Admin chatbot page | `frontend/admin-chatbot.html` + `frontend/admin-chatbot.js` |
| Shared styling | `frontend/style.css` |
| API base URL for frontend | `frontend/config.js` |
| Database connection / in-memory fallback | `backend/app/db.py` |

---

## Step 10: Enable the AI chatbot (optional — needs API keys)

Without API keys the chatbot gives rule-based template answers and
says so in the UI — fully usable. With keys it gives real answers
grounded in the banking SOP documents.

**1. Get keys:**
- `GEMINI_API_KEY` → [aistudio.google.com](https://aistudio.google.com)
- `QDRANT_URL` + `QDRANT_API_KEY` → [cloud.qdrant.io](https://cloud.qdrant.io) (free tier works), or run locally: `docker run -p 6333:6333 qdrant/qdrant`

**2. Add to `backend/.env`:**
```
GEMINI_API_KEY=your_key_here
QDRANT_URL=https://your-cluster.qdrant.io
QDRANT_API_KEY=your_qdrant_key_here
```

**3. Index the banking SOPs** (once, and any time SOP docs change):
```bash
cd backend
python -m app.rag.knowledge_base
```
Expect: `5 document(s) → 39 chunks`, then `BM25 index saved`.

**4. Restart the server** — chatbot now uses real Gemini answers.

The BM25 index is built automatically even without API keys. Only the
Gemini answer-generation step needs `GEMINI_API_KEY`. See
`docs/RAG_CHATBOT.md` for the full setup.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `command not found: python` | Try `python3`; or Python is not on your PATH — see Step 1 |
| `ModuleNotFoundError: No module named 'fastapi'` | Venv is not activated — re-run the Step 3b command, confirm `(venv)` in your prompt |
| `pip install` hangs / connection error | No internet access to `pypi.org` — try a phone hotspot |
| `banking_complaints.csv` not found on startup | Run Step 5b (`python -m data.clean_banking_dataset`) first |
| Startup shows "Seeded 0 banking complaints" | Check that `banking_complaints.csv` exists in `backend/data/` |
| Password rejected at signup | Needs 8+ chars, one uppercase, one of `! @ # $ % ^ & *` |
| Complaint rejected (400) from API directly | Must be 20–1000 characters; city (if sent) must be in `GET /cities` |
| Frontend shows "Failed to fetch" | Backend is not running, or on a different port than `API_BASE` in `config.js` |
| "Invalid or expired session token" | Logged out or backend restarted (in-memory sessions reset) — log in again |
| "Admin access required" (403) | Logged in as customer — use the admin email/password from the backend terminal |
| Chatbot gives template answers | Expected without `GEMINI_API_KEY` — see Step 10 |
| `pytest` fails on `test_bm25_index_covers_banking_keywords` | Run `python -m app.rag.knowledge_base` to rebuild the BM25 index |
| ML model predicts wrong category | Retrain: `python -m app.ml.train_classifier` — check `category_metrics.json` |
| "Address already in use" on port 8000 | Add `--port 8001` to uvicorn and update `config.js` |

---

## A short glossary

- **`ticket_no`** — unique number per complaint (starts at 100001)
- **Session token** — opaque string returned on login, sent as `Authorization: Bearer <token>`; `user_id` is derived from this server-side, never trusted from the client body
- **IDOR** — Insecure Direct Object Reference; prevented here by deriving `user_id` from the session token, not the request body (see DECISIONS.md #9)
- **RAG** — Retrieval-Augmented Generation; search a knowledge base first, then pass the matching snippets to an LLM as context — used by the chatbot (see `docs/RAG_CHATBOT.md`)
- **Distant supervision** — generating training labels from a rule-based heuristic instead of hand-labeling; used for Algorithm 2 priority labels (CFPB has no priority column)
- **TF-IDF** — turns text into a vector of word-importance scores; used by Algorithm 1 to represent complaint text for Logistic Regression
- **In-memory fallback** — when MongoDB is not configured, the app uses a Python dict in place of the real database; data resets on server restart

---

## Where to go next

- `docs/ALGORITHMS.md` — how both ML algorithms actually work, with real accuracy numbers and documented bugs
- `docs/DECISIONS.md` — every non-obvious architectural choice, including Decision 34 (the full banking pivot)
- `docs/API_REFERENCE.md` — every endpoint's exact request/response shape
- `docs/ARCHITECTURE.md` — the big-picture system design
- `backend/data/EDA.md` — full dataset EDA report
