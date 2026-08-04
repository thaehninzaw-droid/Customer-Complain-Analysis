# Loopline

Customer complaint classification system - undergraduate thesis.
Customers file complaints and track their status; two ML algorithms
auto-categorize and auto-prioritize every complaint; an admin
dashboard gives real-time filtering, analytics, and an AI chatbot
grounded in support SOPs.

## Layout

```
loopline/
├── backend/     FastAPI + MongoDB (or zero-setup in-memory fallback)
│                see backend/README.md to run it
├── frontend/    Plain HTML/CSS/JS - customer portal + admin portal,
│                both wired to the real backend (no localStorage left)
├── docs/        Full documentation set - see the map below
└── ROADMAP.md    What's done, what's next, what's a known gap
```

## Start here

- **Brand new to this codebase, or to backend dev in general?** Read
  `docs/GETTING_STARTED.md` - a step-by-step setup guide that assumes
  nothing, written for anyone picking this up for the first time.
- **New to the project, or picking this back up after a break?** Read
  `ROADMAP.md` first - status at a glance, then `docs/DECISIONS.md`
  for the full "why" behind every major choice.
- **Running the backend locally?** `backend/README.md` (or
  `docs/GETTING_STARTED.md` if you want the fully-explained version).
- **Understanding the two ML algorithms** (category classification +
  priority prediction - what the thesis' "algorithm" requirement is
  built on)? `docs/ALGORITHMS.md`.
- **Setting up the RAG chatbot** (Gemini + Qdrant)? `docs/RAG_CHATBOT.md`.
- **Deploying for real** (Render/Atlas/Qdrant Cloud, all free-tier)?
  `docs/DEPLOYMENT.md`.
- **Wondering what's actually been tested vs. just written**?
  `docs/TESTING.md` - read this before assuming anything works
  end-to-end without checking.
- **Setting up shared version control for the team?** `docs/GIT_SETUP.md`.

## Current status

Both algorithms are built, trained, and now running against the real
Kaggle dataset (2224 rows - see `docs/ALGORITHMS.md` for real accuracy
numbers and a few real bugs that dataset surfaced and fixed along the
way). The full customer + admin frontend is wired to a real,
session-token-authenticated backend (see `docs/FRONTEND_INTEGRATION.md`),
and the RAG chatbot is implemented against Gemini + Qdrant (see
`docs/RAG_CHATBOT.md`). CI (`.github/workflows/tests.yml`) runs the
full test suite on every push once this is on GitHub - the first
environment with both internet access and the full dependency set
(`fastapi`/`pydantic`/`pytest`/`xgboost`) installed at once, since the
sandbox this was built in had neither (see `docs/TESTING.md` for
exactly what that means and what to check first). Full detail in
`ROADMAP.md`.

## Documentation map

| Doc | What's in it |
|---|---|
| `docs/GETTING_STARTED.md` | Step-by-step local setup for anyone new - assumes nothing |
| `ROADMAP.md` | Status at a glance, next steps, known gaps |
| `docs/ARCHITECTURE.md` | System overview, why it's shaped this way |
| `docs/ALGORITHMS.md` | Both ML algorithms - methodology, bugs found & fixed, how to retrain |
| `docs/RAG_CHATBOT.md` | Gemini + Qdrant setup, architecture, API shapes used |
| `docs/ADMIN_AUTH.md` | Roles, security model, how admin accounts get created |
| `docs/API_REFERENCE.md` | Every endpoint, request/response shapes |
| `docs/TESTING.md` | What's verified vs. reviewed-but-not-run, and why |
| `docs/DEPLOYMENT.md` | Free-tier deployment walkthrough |
| `docs/FRONTEND_INTEGRATION.md` | What changed on the frontend and why |
| `docs/DECISIONS.md` | The full ADR log - every major decision, explained |
| `docs/GIT_SETUP.md` | Getting the team onto one shared GitHub repo |
