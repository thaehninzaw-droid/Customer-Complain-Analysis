# Decisions Log (Loopline backend)

## What this file is, and why it exists

This is what's called an ADR log - "Architecture Decision Record."
It's a common practice at real engineering companies: every time you
make a choice that would be hard or expensive to undo, you write down
*what* you decided, *why*, *what else you considered*, and *what
you're knowingly leaving unsolved for now*.

Why bother? Two reasons that matter a lot for a thesis specifically:

1. In a few weeks, nobody on the team will remember *why* a decision
   was made - only that it was. Committee members almost always ask
   "why did you choose X over Y?" in a defense. This document is how
   you answer that with confidence instead of guessing.
2. It separates "we didn't think of this" from "we thought about this
   and chose to defer it on purpose." The second one is a sign of
   engineering maturity, not a weakness - and it's much better to
   show an examiner a documented, deliberate trade-off than to have
   them find an undocumented gap themselves.

Add a new entry every time the team makes a call that would be
annoying to reverse. Doesn't need to be long - a few honest sentences
per section is enough.

---

## Decision 1: Problem - complaint classification, not loan default

**Context:** The original idea (loan default prediction) was turned
down by the advisor.

**Decision:** Pivoted to classifying customer complaints by category/
department, with a chatbot that recommends a fix.

**Why:** Still satisfies the rubric (algorithm + data analysis +
decision output), but is a fresher problem, and plays to the
"portfolio" goal of the person who proposed it.

---

## Decision 2: Dataset - Comcast Telecom Complaints (Kaggle)

**Context:** Needed a dataset with real complaint text good enough to
classify and to generate a meaningful recommended action from.

**Alternatives considered:** CFPB Consumer Complaint Database (US
government, 13.8M+ records, already has real category-like labels
via its "Product" field).

**Decision:** Stuck with the smaller Comcast dataset (~2,224 tickets).

**Why:** Its complaint text is short and specific, which makes the
chatbot's recommendation clearer to demo. The team also already had
momentum with it.

**Trade-off we're accepting:** This dataset has **no department/
category column** - the team has to invent categories and either
hand-label data or use a rule-based/LLM classifier instead of training
on ground-truth labels. It's also small, so "big data" is true in
spirit more than in scale. If the rubric is strict about dataset size,
this is worth double-checking with the advisor.

---

## Decision 3: MongoDB (NoSQL)

**Decision:** MongoDB for storage - both because the assignment
required a NoSQL database, and because a complaint document (freeform
text + a handful of fields) doesn't need relational structure.

---

## Decision 4: Category list - provisional, pending team confirmation

**Context:** Once we looked at the actual frontend code, we found
*three different category lists* already in use across different
pages (the survey form, the new-complaint form, and our own backend
placeholder) - a sign the same business data was being hand-typed in
multiple places instead of defined once.

**Decision:** Adopted the new-complaint form's list as canonical for
now: Billing, Financial, Technical, Service, Others. Built a single
`app/categories.py` module as the one place this list lives - the
classifier, the chatbot templates, and a new `GET /categories`
endpoint all read from it, so nothing else hardcodes it again.

**Known issue, not yet resolved:** "Billing" and "Financial" overlap
heavily in practice (both are about money). Flagged to the team -
still waiting on a final answer.

---

## Decision 5: Classification algorithm - keyword baseline first

**Decision:** Started with a simple keyword-matching classifier
(`app/classify.py`) rather than a trained model.

**Why:** It's something the team can understand and modify
immediately, and it unblocks every other part of the system (storage,
dashboard, chatbot) without waiting on a data-labeling effort.

**Design pattern used - Strategy Pattern:** The rest of the codebase
only ever calls `classify_complaint(text) -> category`. It has no
idea *how* that decision gets made. That's on purpose: it means the
keyword version can be swapped for a trained model (e.g. Naive Bayes
or Logistic Regression on TF-IDF features) later, and nothing that
calls it has to change. This is a real, named design pattern (worth
citing in the thesis writeup): you're decoupling "what gets decided"
from "how it gets decided."

**Deferred:** Actually training a real ML model on hand-labeled data.
Worth doing before the deadline if there's time, both because it's a
stronger "algorithm" for the rubric and because it'll classify more
accurately than keyword matching.

---

## Decision 6: Password hashing - PBKDF2 (standard library), not bcrypt

**Decision:** `app/security.py` uses Python's built-in `hashlib`
(PBKDF2-HMAC-SHA256 with a random salt) instead of adding a `bcrypt`
dependency.

**Why:** No new dependency to install (this sandbox had no internet
access to test one), and it's still enormously better than the plain-
text passwords the frontend demo currently stores in `localStorage`
(which is fine for a pure front-end demo, not fine for a real
database). If the team wants to swap to bcrypt/argon2 later, only
this one file changes.

---

## Decision 7: MongoDB with an in-memory fallback for local dev

**Decision:** `app/db.py` uses real MongoDB when `MONGODB_URI` is set,
and an in-memory Python store when it isn't.

**Why:** Lets anyone run and test the whole API on their laptop
before MongoDB Atlas is set up - useful given the team is still
deciding on infrastructure.

---

## Decision 8: Backend schema matches the frontend's existing code, not the other way around

**Context:** The frontend (built ahead of the backend) already stores
complaints client-side with specific field names - `ticket_no,
category, complaint, date_month_year, time, city, state, zipcode,
status, user_id` - and has comments marking exactly which endpoints
it expects (`POST /auth/signup`, `GET /issues/pulse`).

**Decision:** Matched the backend's field names, ticket-numbering
scheme (starts at 100001, increments off the current max), and
endpoint paths to what the frontend already assumes.

**Why:** Far less rework for whoever wires the frontend up to a real
backend - the contract was already half-written, just not visible
until we opened the code.

---

## Decision 9 (today): Session tokens - fixing an IDOR vulnerability

**Context:** The original `/complaints` endpoints accepted a
`user_id` directly from the client and trusted it. That meant anyone
calling the API could read or file complaints *as any other user* just
by changing a number in the request - no proof required. This class
of bug has a name - **IDOR (Insecure Direct Object Reference)** - and
it's common enough to be on the [OWASP Top 10](https://owasp.org/www-project-top-ten/)
list of web application risks.

**Decision:** Added `app/sessions.py` - signup/login now return an
opaque session token, and any endpoint that needs to know "who is
calling" (filing a complaint, listing "my" complaints) requires
`Authorization: Bearer <token>` and derives the user_id from that
token server-side, never from the request body.

**Alternatives considered:** JWTs (JSON Web Tokens) - the more
"standard" approach, but adds complexity (expiry, signing keys) we
don't need to solve today.

**What's still open:** `GET /admin/complaints` is intentionally left
without any access control - it exists so the admin dashboard has
something to call, but it returns every customer's data to anyone
right now. It's clearly marked in code as temporary. This can't be
properly fixed until the team decides who owns "admin login" (see
Open Questions below) - at that point, the same pattern
(`get_current_user_id`-style dependency) should be reused, just
checking "is this caller an admin" instead of "who is this caller."

---

## Decision 10: Priority prediction (Algorithm 2) - sentiment/urgency features + boosted trees

**What:** a second algorithm, matching the hand-drawn flowchart's
"Algorithm 2: Priority Prediction (e.g., Sentiment/ML)" - a lexicon-
based sentiment/urgency scorer (`app/sentiment.py`) feeds a rule-based
baseline (`app/priority.py`) AND a set of engineered features for a
trained gradient-boosted-trees model (`app/ml/train_priority.py`).
Same two-layer dispatcher design as Algorithm 1.

**Why not just reuse Algorithm 1's approach wholesale:** priority
isn't a topic-classification problem the way category is - it's more
about *how* something is said (urgency, tone) than *what* it's about.
TF-IDF alone is a bad fit; sentiment/urgency signals plus a small
amount of TF-IDF context turned out to work well together.

**Training labels:** same distant-supervision approach as Decision 5 -
the rule-based baseline bootstraps labels for the trained model. See
docs/ALGORITHMS.md for the full methodology writeup, including two
real bugs found and fixed in the sentiment lexicon along the way
(broken negation detection, a "never"-inside-"whenever" substring
collision) - worth reading if this gets questioned in a defense, since
"were the bugs found through testing or just assumed away" is exactly
the kind of question worth having a real, honest answer to.

**Thresholds:** Low/Medium/High cutoffs were calibrated against the
actual score distribution of the training corpus (roughly the 60th/
90th percentiles) rather than picked arbitrarily - see
`predict_priority_baseline()`'s docstring.

## Decision 11: XGBoost unavailable in the dev sandbox - scikit-learn substitute

The SRS names XGBoost specifically. It's not installed in the
environment this was built in (no internet access there to `pip
install` it). `train_priority.py` tries `from xgboost import
XGBClassifier` first and falls back to scikit-learn's
`HistGradientBoostingClassifier` - same algorithm family (gradient-
boosted decision trees), same interface - if that import fails.
`requirements.txt` lists `xgboost` normally, since it's expected to
install fine anywhere with real internet access; this is a sandbox
limitation being worked around, not a decision to avoid XGBoost. See
docs/ALGORITHMS.md and docs/TESTING.md.

## Decision 12: Synthetic dataset generator for offline development

The real Kaggle Comcast dataset needs internet access to download,
which wasn't available while building this. `data/generate_synthetic_
dataset.py` produces a same-schema, clearly-labeled-as-synthetic
stand-in so the ML pipeline could be built AND actually run/tested
end-to-end, rather than written and left unverified. Swapping in the
real dataset later is a drop-in replacement - see docs/ALGORITHMS.md's
"the dataset" section for the exact mechanics and the warning against
citing synthetic-data accuracy numbers as real-world performance.

## Decision 13: Admin roles and auth - closing the security gap, matching the SRS's "log in only"

Two things landed together because they're really the same fix:

1. `/admin/complaints` had **zero authentication** before this round -
   anyone who found the URL could read (and, once the manual-entry/
   edit endpoints existed, write) every complaint in the system. This
   is now behind `get_current_admin_id` (see docs/ADMIN_AUTH.md) -
   requires a valid session token AND `role == "admin"`.
2. The SRS PDF itself resolves the "is admin login required" open
   question from before: its landing-page nav explicitly separates
   "Customer Login / Sign Up" from "Admin Login **< log in only >**" -
   i.e., required, and no public signup. There's no `/admin/signup`
   anywhere; admin accounts are seeded server-side only (`app/
   admin_seed.py`), auto-run on API startup for zero-setup local dev,
   plus a standalone script (`data/seed_admin.py`) for real deployments.

## Decision 14: RAG chatbot stack - Gemini + Qdrant, via REST rather than SDKs

Stack specified directly (Gemini for embeddings + generation, Qdrant
for vector storage). Implemented via plain `requests` calls against
each service's REST API rather than the official `google-genai` /
`qdrant-client` SDK packages - neither package is installed in the dev
sandbox and there's no internet access there to add or test them, and
a REST-based wrapper is one fewer dependency that has to install
correctly elsewhere. The exact request/response shapes were verified
against live API documentation while building this (cited in
docs/RAG_CHATBOT.md), not pulled from training-data memory, since
model names and API details are exactly the kind of thing that goes
stale. **Not yet tested against the real services** - see
docs/TESTING.md.

Both the customer-facing widget and the Admin AI Chatbot fall back to
a static template if Gemini isn't configured or a call fails - same
"never let an AI integration break the request" pattern as the two ML
algorithms' rule-based baselines.

## Decision 15: Removed customer-side complaint editing (moved to admin-only)

The original prototype let a logged-in customer edit their own
complaint's category/status directly from the Activities page (an
artifact of frontend-only development with no server-side
authorization to enforce anything else). The SRS itself frames this
differently: "Edit complaint details" / "Update complaint status" are
listed under the Admin Dashboard (Module 3.1), while the Customer
Portal section only describes a read-only "Complaint History & Status
Tracking" view. Now that real authorization exists, the UI was
brought in line with the written spec: that editing capability was
removed from the customer-facing Activities page and is now
`PATCH /admin/complaints/{ticket_no}`, admin-only. See
docs/FRONTEND_INTEGRATION.md for the full before/after.

## Decision 16: Admin frontend built reusing the existing design system

`admin-login.html` / `admin-dashboard.html` / `admin-chatbot.html`
deliberately extend Loopline's existing tokens/components
(`style.css`'s teal/amber palette, Fraunces/Inter/Plex Mono type
system, existing `.card`/`.btn`/`.modal`/`.status-badge` components)
rather than inventing a separate visual identity for "the admin side."
For a product that already has an established look, consistency
across customer- and admin-facing surfaces is the right call - a
visually disconnected admin panel would read as a bolted-on afterthought
rather than part of the same product. One deliberate extension: IBM
Plex Mono (already used for ticket numbers/dates elsewhere) is carried
through to the new priority badges and ML-model-accuracy metrics, since
that's an existing "this is data" visual motif in the app, not a new one.

## Decision 17: Real Kaggle dataset loaded - and what actually broke when it was

The real dataset (2224 rows, downloaded from Kaggle - see
`backend/data/comcast_complaints.csv`) replaced the synthetic stand-in
the moment it was available, with zero code changes needed to the
training scripts themselves (that was the entire point of Decision
12). But loading it end-to-end surfaced four real, non-obvious bugs
that a synthetic dataset built by the same assumptions as the code
would never have caught - worth recording exactly because "I tested it
against my own synthetic data and it worked" is a weaker claim than it
sounds, and this is the concrete reason why:

1. **Date format mismatch** - the real CSV's dates (`"DD-MM-YY"`)
   don't match this app's internal format (`"YYYY-MM-DD"`); loading
   them unconverted would have silently zeroed out the admin
   dashboard's "Monthly Volume" chart for every imported row. Fixed in
   `data/load_dataset.py`.
2. **A fixed "last 12 months" window doesn't work for old data** - the
   monthly volume chart was windowed relative to *today*, which never
   overlaps a dataset that's entirely from 2015. Fixed by windowing off
   the data's own date range in `app/analytics.py` instead.
3. **Status vocabulary mismatch** - the real data uses "Solved"/"Open"
   where this app uses "Resolved"/"Pending". Normalized on import
   (`data/load_dataset.py`'s `STATUS_MAP`) rather than teaching every
   status-aware piece of code a second vocabulary.
4. **numpy scalar types leaking out of both trained models** -
   harmless for JSON/Pydantic (numpy.str_ is a str subclass) but fatal
   for real MongoDB's BSON encoder, and independently responsible for
   a `numpy.bool_(False) is False -> False` gotcha in a unit test. Only
   found by actually tracing what pymongo would do with the resulting
   documents - the in-memory DB fallback used throughout this build
   doesn't care about types, so it never would have caught this.

None of these were hypothetical edge cases - all four would have
silently produced wrong or empty output with the real, 2224-row
dataset that's now the project's actual data. See docs/ALGORITHMS.md
for the full writeup of each, including the real per-category metrics
now available (93.0% category accuracy, 100% priority accuracy vs.
their respective baseline labels) and a genuinely interesting finding
in the data itself (47% of all complaints landed in June 2015 alone).

## Decision 18: CI via GitHub Actions

Added `.github/workflows/tests.yml`, running `pytest` (plus a
`py_compile` sanity pass) on every push and pull request, using a real
GitHub-hosted runner with actual internet access - which is exactly
what this local dev sandbox has lacked throughout this build (see
docs/TESTING.md). This is the first environment in this project's
history where the full FastAPI/pydantic-dependent test suite
(`tests/test_api.py`) can actually run automatically, not just be
reviewed by eye. See docs/TESTING.md's "before you trust this" section
- CI passing is a meaningfully stronger signal than everything
described there, once it's set up and green.

**Update: confirmed green** after pushing to GitHub. This validated,
for the first time anywhere, the entire FastAPI HTTP layer (including
the admin auth/authorization checks - see Decision 13) and the real
XGBoost training path (see Decision 11) - both previously only
reviewed by eye. What CI does NOT cover (no secrets configured, by
design): real Gemini/Qdrant calls, real MongoDB Atlas - both still
genuinely untested anywhere. See docs/TESTING.md for the current,
precise breakdown of what's confirmed vs. still open.

## Open questions - not yet decided by the team

- ~~**RAG chatbot stack:** which LLM and vector database?~~ **Resolved
  (Decision 14):** Gemini + Qdrant.
- ~~**Admin login:** who owns/builds it, and is it required at all?~~
  **Resolved (Decision 13):** required (the SRS itself says so - see
  that decision), built, and secured.
- **Final category list:** Billing/Financial overlap still unresolved.
  Nothing in this round of work touched the taxonomy itself - still a
  real open question for the team (e.g., is a billing dispute "Billing"
  or "Financial"? Both categories exist in the SOP knowledge base with
  slightly different framing - see data/knowledge_base/ - but the line
  between them is still fuzzy).
- **Thesis rubric specifics:** confirmed there must be an algorithm,
  data analysis, and a final decision/recommendation - but no written
  rubric has been shared yet to check against in detail. (This round
  added a second algorithm, which only helps regardless of the exact
  rubric wording.)

---

## Not done yet (known gaps, not oversights)

Being upfront about these matters as much as the decisions above:

- Local git repo exists (see docs/GIT_SETUP.md) but still needs to be
  pushed to a real GitHub remote by the team - that step needs a real
  GitHub account/credentials this environment doesn't have.
- Session tokens never expire. Fine for a demo, not for anything real
  - applies to admin sessions too now, arguably higher-stakes there.
- No rate limiting, no logging, no monitoring - not needed at this
  scale, but worth a one-line mention in the thesis as "aware of, out
  of scope."
- ~~The classifier is still rule-based, not a trained model.~~
  **Resolved** - see Decision 10 and docs/ALGORITHMS.md. Both
  algorithms now have a trained-model layer with a rule-based fallback.
- **New gaps from this round:**
  - The entire FastAPI HTTP layer, the real Gemini/Qdrant API calls,
    and real MongoDB are untested in the sandbox this was built in (no
    internet access, `fastapi`/`pydantic`/`pytest` not installed) - see
    docs/TESTING.md for exactly what that means and what to check first.
  - XGBoost (the algorithm the SRS names for priority prediction) isn't
    installed in that sandbox either - `train_priority.py` auto-falls-
    back to a scikit-learn equivalent; see Decision 11.
  - No password reset flow, no admin permission levels, no audit log
    of admin edits - see docs/ADMIN_AUTH.md's "what's still not built"
    section for the full list.
  - CORS is wide open (`allow_origins=["*"]`) - fine for development,
    needs tightening before a real deployment (see docs/DEPLOYMENT.md).
  - The homepage survey/contact forms are still client-only demos, not
    wired to any backend - see docs/FRONTEND_INTEGRATION.md for why
    that was a deliberate scope call, not an oversight.
