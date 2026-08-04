# Architecture

## System overview

```
                        ┌──────────────────────────┐
                        │   Public Landing Page    │
                        │  (index.html)            │
                        └───────────┬──────────────┘
                                    │
                 ┌──────────────────┼──────────────────┐
                 ▼                                     ▼
     ┌───────────────────────┐          ┌───────────────────────────┐
     │   Customer Portal      │          │      Admin Portal          │
     │  login/signup/         │          │  admin-login.html          │
     │  activities.html        │          │  admin-dashboard.html      │
     │  (file/track complaints)│          │  admin-chatbot.html        │
     └───────────┬─────────────┘          └────────────┬───────────────┘
                 │  fetch() + Bearer token              │  fetch() + Bearer token
                 ▼                                      ▼
     ┌─────────────────────────────────────────────────────────────────┐
     │                     FastAPI backend (backend/app)                │
     │                                                                    │
     │  /auth/*         session-token auth (app/auth.py, sessions.py)    │
     │  /complaints     Algorithm 1 + Algorithm 2 run here on submit     │
     │  /admin/*        role-checked (get_current_admin_id)               │
     │  /chatbot/*      RAG pipeline (app/rag/) or template fallback      │
     └───────┬────────────────┬───────────────────┬──────────────────────┘
             │                │                   │
             ▼                ▼                   ▼
   ┌──────────────────┐ ┌─────────────────┐ ┌────────────────────────┐
   │ MongoDB Atlas     │ │  app/ml/         │ │  Gemini API + Qdrant    │
   │ (or in-memory      │ │  Algorithm 1: TF-│ │  (or in-memory fallback │
   │  fallback - db.py) │ │  IDF+LogReg      │ │  - app/rag/)            │
   │                    │ │  Algorithm 2:    │ │                          │
   │                    │ │  sentiment + GBT │ │                          │
   └──────────────────┘ └─────────────────┘ └────────────────────────┘
```

## Why this shape

**Everything has a zero-setup path.** Clone the repo, `pip install`,
`uvicorn app.main:app --reload` - it runs immediately with an
in-memory database, a keyword-based classifier, a rule-based priority
heuristic, and a template chatbot. Every "real" upgrade (MongoDB,
trained ML models, Gemini, Qdrant) is a config/script step that
upgrades the SAME code path rather than a different one - see
`app/db.py`, `app/classify.py`, `app/priority.py`, `app/rag/
vector_store.py` for the pattern repeated four times. This matters a
lot for a school project: whoever's grading it, or a teammate on a
laptop with no accounts set up yet, gets a fully working demo with
zero configuration.

**Auth is session-token based, not "trust the client."** The original
frontend-only prototype stored a `user_id` in localStorage and sent it
back to "prove" identity - anyone could open devtools and pretend to
be a different user (see DECISIONS.md #9, the IDOR fix). Now:
`/auth/login` returns an opaque token, the frontend sends it back as
`Authorization: Bearer <token>`, and the backend resolves that token
to a real user_id server-side (`app/sessions.py`). Admin endpoints
layer a role check on top of the same mechanism
(`get_current_admin_id` in `app/main.py`) rather than being a separate
system.

**Two algorithms, same dispatcher pattern.** Category classification
(Algorithm 1) and priority prediction (Algorithm 2) each have a public
function (`classify_complaint()`, `predict_priority()`) that tries a
trained ML model first and falls back to a rule-based baseline if no
model has been trained yet. Nothing that calls these functions needs
to know or care which path ran - see docs/ALGORITHMS.md.

**The RAG chatbot is additive, not required.** `/chatbot/recommend`
and `/admin/chatbot/ask` both work with zero configuration (template
responses), and upgrade to real Gemini+Qdrant-backed answers the
moment `GEMINI_API_KEY` is set - see docs/RAG_CHATBOT.md.

## Directory layout

```
loopline/
├── backend/
│   ├── app/
│   │   ├── main.py            FastAPI app + all routes
│   │   ├── models.py          Pydantic request/response schemas
│   │   ├── auth.py            signup validation, password hashing glue
│   │   ├── admin_seed.py       demo admin account bootstrap
│   │   ├── security.py         PBKDF2 password hashing
│   │   ├── sessions.py         opaque token -> user_id
│   │   ├── db.py               MongoDB / in-memory switch
│   │   ├── categories.py       single source of truth for the 5 categories
│   │   ├── cities.py            single source of truth for the 63-city Myanmar city/state/zip lookup
│   │   ├── validation.py        server-side complaint length + city checks (POST /complaints, POST /admin/complaints)
│   │   ├── classify.py         Algorithm 1 dispatcher + keyword baseline
│   │   ├── priority.py         Algorithm 2 dispatcher + rule-based baseline
│   │   ├── sentiment.py        lexicon-based sentiment/urgency scorer
│   │   ├── tickets.py          ticket number generation
│   │   ├── pulse.py            homepage "pulse" chart data
│   │   ├── analytics.py        admin dashboard aggregate stats
│   │   ├── chatbot.py           chatbot entry points (customer + admin)
│   │   ├── ml/                 trained-model layer for Algorithm 1 + 2
│   │   │   ├── train_classifier.py
│   │   │   ├── train_priority.py
│   │   │   ├── classifier_model.py
│   │   │   ├── priority_model.py
│   │   │   ├── features.py
│   │   │   └── artifacts/       (generated .joblib files + metrics.json)
│   │   └── rag/                 RAG pipeline for the Admin AI Chatbot
│   │       ├── gemini_client.py
│   │       ├── vector_store.py
│   │       ├── knowledge_base.py
│   │       └── pipeline.py
│   ├── data/
│   │   ├── generate_synthetic_dataset.py
│   │   ├── load_dataset.py
│   │   ├── seed_admin.py
│   │   ├── sample_complaints.csv
│   │   ├── synthetic_complaints.csv  (generated)
│   │   └── knowledge_base/        SOP markdown docs indexed by the chatbot
│   ├── scripts/
│   │   └── manual_api_smoke_check.py  live-HTTP end-to-end check, see docs/TESTING.md
│   └── tests/
├── frontend/
│   ├── index.html, login.html, signup.html, activities.html   (customer)
│   ├── admin-login.html, admin-dashboard.html, admin-chatbot.html  (admin)
│   ├── config.js, auth.js, script.js, admin.js, admin-dashboard.js,
│   │   admin-chatbot.js
│   └── style.css
├── docs/                        you are here
└── ROADMAP.md
```
