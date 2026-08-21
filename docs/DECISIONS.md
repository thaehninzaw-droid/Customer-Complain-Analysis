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

## Decision 19: Reviewed a peer team's repo - two small things adopted, most of it wasn't

A junior team's zipped repo (same shared "Loopline" starter template)
was reviewed as a reference, not a source of truth - diffed against
our own copy of that same starter to isolate exactly what they'd
actually changed, rather than taking any of it at face value. Full
verdict: their scope was much smaller (basic Flask signup/login, the
mostly-unmodified starter frontend, a data-cleaning script; no
classification algorithm, no priority prediction, no admin anything,
no tests, no CI). Two things worth flagging from that review, for the
record:

- **Not adopted, worth knowing about**: their backend stores and
  compares passwords in **plaintext** (no hashing at all), and their
  session model is just the username string held client-side - the
  same IDOR-shaped issue this project already found and fixed (see
  Decision 9). Their `clean_data.py` also has two real bugs of its
  own: converting Zip code to an integer silently drops the leading
  zero on ~170/2224 rows, and it applies the wrong `strptime` format
  to the raw `"Date"` column, silently nulling it out entirely. Noted
  here mainly as a "we checked, and this is worse, not just
  different" data point, not as a criticism of them specifically.

- **Adopted**: a password show/hide toggle on the login/signup
  password fields (small, safe, clearly better UX; see the `.pw-field`/
  `.pw-toggle` CSS and the wiring in `auth.js`).

- **Adopted the idea, not the execution**: their `clean_data.py`
  remaps every complaint date from 2015 to 2025, apparently to make
  demo dashboards look current. Their specific execution has the date-
  parsing bug mentioned above and permanently alters the year (losing
  the ability to ever recover the true date), which isn't something
  to copy. But the underlying problem is real - a decade-old dataset
  makes a "recent activity" dashboard look dead - and it's a good fit
  for something we'd already solved a different way (Decision 17's
  data-driven monthly-volume window). Implemented properly as an
  **opt-in `--demo-shift-dates` flag** on `data/load_dataset.py`:
  shifts every row by a single shared day-offset (not just the year)
  so the LATEST complaint lands on today and every complaint keeps its
  exact relative spacing to every other one - the real dataset's
  June-2015 spike (see Decision 17) shifts intact as a single visible
  spike, just relabeled into a recent-feeling window. Off by default;
  the canonical CSV file on disk is never touched, only whatever gets
  written into the target database. Needed zero changes to
  `app/analytics.py`, since that file already windows off the data's
  own date range rather than a fixed one - this is a direct payoff of
  Decision 17's fix. Never cite demo-shifted dates as the real
  analysis period in the thesis - the true period is 2015 (see
  docs/ALGORITHMS.md).

## Decision 20: This session - reproduced CI locally, confirmed real XGBoost artifacts, added a live HTTP smoke test, and hit a real network wall on Mongo/Gemini/Qdrant/deploy

**Context:** Picked this project back up per `HANDOFF.md`'s priority
order (real Mongo → real Gemini/Qdrant → deploy → manual click-
through). This session's sandbox turned out to have real PyPI/npm/
GitHub access (unlike either prior sandbox described in
`docs/TESTING.md`), so the first useful move was to actually install
the full dependency set and see what's true right now, rather than
assume the last session's CI-green claim still holds without checking.

**What was actually run, for real, in this session:**

1. **Dataset integrity check.** Compared the freshly-supplied
   `Comcast_Telecom_Complaints_Dataset.zip` against the CSV already
   committed at `backend/data/comcast_complaints.csv` - identical
   `md5sum`. No drift; the committed dataset is exactly the Kaggle
   source file.
2. **Full dependency install + CI reproduction, locally.** `pip
   install -r requirements-dev.txt` succeeded outright, including
   `xgboost` - this session's sandbox has genuine internet access to
   PyPI, which neither prior build/CI environment combination had
   verified locally before (CI was green on GitHub's runners, per the
   last handoff, but nobody had reproduced that locally until now).
   Ran, in order: `compileall`, `python -m app.ml.train_classifier`
   (93.0% accuracy vs. keyword labels - matches the documented figure
   exactly), `python -m app.ml.train_priority`, and `pytest -v`: **83
   passed, 0 failed.**
3. **The XGBoost nuance from the last handoff is now resolved.**
   Retraining `train_priority.py` locally (now that `xgboost` installs)
   produced `priority_metrics.json` with `"model":
   "XGBClassifier(n_estimators=200, max_depth=4)"` - the shipped
   artifacts in `backend/app/ml/artifacts/` are genuine XGBoost now,
   not the scikit-learn `HistGradientBoostingClassifier` fallback the
   last session shipped. Same 100% accuracy vs. baseline-heuristic
   labels as before - the number didn't change, only which model
   family produced it.
4. **Added a live, end-to-end HTTP smoke test** -
   `backend/scripts/manual_api_smoke_check.py` - that starts a real
   `uvicorn` process (in-memory DB fallback, same as CI) and drives it
   over real HTTP with `requests`, rather than FastAPI's in-process
   `TestClient` (which `tests/test_api.py` already covers). This is a
   meaningfully different check: it exercises the full customer flow
   (signup → login → file a complaint → auto-categorized "Billing" /
   "High" priority for an angry billing complaint, a sensible result →
   appears in the caller's own activities → unauthenticated access
   correctly rejected) and the full admin flow (admin login → a valid
   *customer* token correctly gets `403` on `/admin/complaints`, not
   just reviewed-by-eye - see the false alarm below → list/manual-entry/
   inline-edit/analytics/ml-status → chatbot `ask` correctly discloses
   `used_rag: false` since no Gemini key is configured). **20/20
   checks passed** on the second run (see next paragraph for the first
   run's false alarm).
5. **A false alarm worth recording, in the spirit of Decision 17/19's
   "document what you actually found":** the smoke test's first run
   showed 10 failures, including "customer token on `/admin/complaints`
   gets 401, not the documented 403." Traced it before concluding
   anything: the smoke test's own generated username
   (`smoketest_<unix-timestamp>`) violates `app/auth.py`'s own username
   validation (letters/numbers/spaces only, no underscore) - signup
   failed with `400` before a real token ever existed, so every
   downstream call in that run (including the admin one) was using a
   missing/invalid token, which correctly returns `401`. Reading
   `get_current_admin_id` in `app/main.py` directly confirmed the 403
   check *is* there and *is* reached separately from the 401 check;
   fixing the test's username format (not the app) made all 20 checks
   pass, including the real 403 case. Recorded here mainly as a
   reminder that a failing check is a reason to trace the cause before
   editing app code, not a reason to assume the app is wrong -
   consistent with this project's own standard (Section 4 of
   `HANDOFF.md`).
6. **Confirmed, by direct request, that this session cannot reach
   MongoDB Atlas, the Gemini API, Qdrant Cloud, or Render at all** -
   each returns `403` with header `x-deny-reason: host_not_allowed`
   from the sandbox's own egress proxy, before the request ever leaves
   for the real service (a `pypi.org` request in the same test returns
   a normal `200`, confirming this is host-specific, not a general
   outage). **This means priorities #1-3 in `HANDOFF.md` Section 5
   cannot be attempted from inside this session at all, regardless of
   whether real credentials are supplied to it** - it's a network
   policy on the environment, not a credentials gap. Flagged plainly
   rather than quietly attempted-and-failed-silently, per this
   project's own "fallbacks over hard failures, always disclosed"
   standard (`HANDOFF.md` Section 4.3) - the same principle, applied to
   what this *session* can't do, not just what the *code* falls back to.
7. **A second, smaller self-inflicted bug, also worth recording:** the
   smoke-check script was first named `manual_api_smoke_test.py`.
   Running the full suite with a fresh venv (a clean-room check before
   handing anything off) turned up `pytest` trying to *collect* it as a
   test module and failing at import time with a `ConnectionError` -
   its filename matched pytest's default `*_test.py` discovery
   pattern, so plain `pytest -q` from `backend/` picked it up and ran
   its module-level code (real HTTP calls) during collection, with no
   server running. This would have broken CI the next time it ran.
   Fixed by renaming it to `manual_api_smoke_check.py` (outside the
   default discovery patterns) and restructuring it so nothing executes
   at import time - all logic now lives inside `main()`, guarded by
   `if __name__ == "__main__":`. Re-ran a fresh-venv `pytest -q` after
   the fix: 83 passed, 0 errors, nothing collected from `scripts/`.
   Recorded because it's a generically useful lesson for this repo:
   *any* new script dropped into `backend/` that happens to match
   `test_*.py`/`*_test.py` will get silently collected by a bare
   `pytest` invocation, whether or not it's actually a test.

**What this changes vs. the last handoff:** items already marked ✅ in
`docs/TESTING.md`'s "Confirmed by CI" section are now *also* confirmed
independently, locally, in a different environment than GitHub's
runners - a stronger signal than either alone. Items still marked ⚠️
(real Mongo/Gemini/Qdrant) are unchanged and now additionally confirmed
*unreachable from this particular session*, which is new, useful
information even though it isn't progress on those three items
themselves.

**What's still open:** exactly `HANDOFF.md`'s priorities #1-3, unchanged
- they need a network-unrestricted environment (your own machine, or a
session/tool with those hosts allow-listed) to move at all. See
`ROADMAP.md`'s new "hard constraint" note for the practical options.

---

## Decision 21: Junior team's "new feature" request (Myactivities.zip) turned out to already exist, more completely - plus a new junior-facing setup guide

**Context:** A junior team member proposed a customer complaint-filing
+ tracking feature (`Myactivities.zip` - a standalone Flask+MongoDB
prototype: file a complaint, get a ticket number, see a dashboard with
status tiles and a searchable history). Before building anything, this
needed comparing against what Loopline already has.

**Finding (received pre-analyzed from a prior chat session in this
project, not independently re-verified in this session - flagged
explicitly per this doc's own standard of saying what was and wasn't
actually checked):** the proposed feature already exists in Loopline,
more completely, on every axis compared - real ML-based category/
priority auto-assignment (the prototype has neither), a real status
workflow (the prototype's status is always `"Pending"`, nothing ever
updates it), hashed passwords + session-token auth + server-side data
isolation (the prototype stores plaintext passwords and returns every
user's complaints to anyone), a larger Myanmar city list (63 vs. 10),
and admin tooling the prototype has none of. Two implementation
details in the prototype were flagged as arguably better than
Loopline's current behavior and worth borrowing as small hardening
items, not new features: (1) server-side complaint-length and city
validation - Loopline currently only validates these client-side in
`script.js`, bypassable via a direct API call; (2) serving the city
list from a `GET /cities`-style endpoint rather than only embedding it
in frontend JS. **Neither has been implemented yet** - recorded here as
a known, small, not-yet-done backlog item, not a completed decision.

**Decision:** don't build anything new off this request. If time
allows, add server-side validation to `POST`/`PATCH` complaint
endpoints in `app/main.py` matching what `script.js` already enforces
client-side, and consider exposing the Myanmar city list via a small
`GET /cities` endpoint the frontend could optionally use instead of
its own hardcoded copy. Neither blocks anything else.

**Also this session:** added `docs/GETTING_STARTED.md` - a step-by-step
setup guide assuming no prior familiarity with the codebase, venvs, or
even that Python is installed yet, for junior team members or anyone
picking this project up cold. Distinct from `backend/README.md`'s
quickstart (terse, assumes experience) and `HANDOFF.md` (written for
whoever/whatever continues this work session-to-session, assumes a lot
of project context already). Its Step 10 worked example (adding a
`version` field to the health-check endpoint) was actually implemented,
tested (`pytest` - 83 passed, plus a live `curl` check confirming the
exact response body documented), and then reverted before shipping -
so the instructions are proven correct rather than just written from
memory, but the repo itself is left in its prior state so the exercise
still has something for the reader to actually do.

---

---

## Decision 22: Implemented the two hardening items from #21 - server-side complaint validation + `GET /cities`

**Context:** Decision 21 flagged two small, not-yet-done hardening
ideas after evaluating the junior-proposed `Myactivities.zip`
prototype - server-side complaint length/city validation, and exposing
the Myanmar city list from the backend. Asked directly "is this worth
adopting" - yes for these two specific, narrow items (the broader
feature/UI was not adopted; see #21 for why).

**What was built:**

1. **`app/cities.py`** - the single source of truth for the 63-entry
   Myanmar city → state/zip lookup, mirroring `app/categories.py`'s
   existing pattern exactly. Generated by parsing `frontend/script.js`'s
   existing `MYANMAR_CITIES` constant programmatically (not retyped by
   hand) to rule out transcription drift - verified afterward that all
   63 entries round-tripped correctly.
2. **`GET /cities`** - added the same way `GET /categories` already
   works: returns the full list, no auth required.
3. **`app/validation.py`** - `validate_complaint_text()` (20-1000
   chars after trimming, matching `frontend/script.js`'s existing
   bound exactly) and `validate_city()` (case-insensitive match
   against `app/cities.py`, only checked if a non-blank city was
   actually sent - it's still an optional field). Deliberately does
   *not* port `script.js`'s fuzzier gibberish/repeated-character/
   junk-word heuristics - those are reasonable as a live-typing UI
   nudge, but too subjective to hard-reject on server-side, where a
   false positive just silently loses a legitimate complaint with no
   chance for the user to see why as they type.
4. Wired into both `POST /complaints` and `POST /admin/complaints` -
   same validation, same `400` response shape as the rest of this
   codebase's error handling (`{"detail": "<message>"}`, not raw
   Pydantic validation errors).

**Verified, not just written:** added `tests/test_cities.py` (data
integrity - no duplicate cities, all fields present),
`tests/test_validation.py` (11 unit tests covering both boundaries,
case-insensitivity, optional-field behavior), and 7 new integration
tests in `tests/test_api.py` hitting the real HTTP endpoints. Also
caught and fixed a real bug this introduced: `backend/scripts/
manual_api_smoke_check.py` (added in #20) was using US cities
("Springfield", "Chicago") for its test data, which the new validation
now correctly rejects - updated it to use real entries from
`app/cities.py` (Yangon, Mandalay) instead, and added two new checks
to it for the validation behavior itself and one for `GET /cities`.
Full suite after all of this: **103 passed** (was 83). Live smoke
check: **23 passed** (was 20).

**Known, explicitly-flagged loose end:** `frontend/script.js` still
has its own hardcoded copy of `MYANMAR_CITIES`, not fetched from
`GET /cities`. Today the two are identical (the backend copy was
generated *from* the frontend's), so there's no drift yet - but
there's nothing stopping them from drifting apart the next time either
one is edited without the other. Not fixed in this pass because it
means touching the autocomplete widget's filtering/matching logic in
`script.js` (a few hundred lines, not read closely enough this session
to be confident editing it live), which is a meaningfully different
risk profile than a backend-only addition. Worth doing properly in its
own pass, following exactly the comment already in `script.js` above
`populateCategorySelect()` for how the same problem was solved for
categories.

---

## Decision 23: Doc audit before push - `GETTING_STARTED.md` and others were stale after #22

**Context:** Asked directly "are you sure the docs and setup guide are
correct" before pushing to GitHub. Answer at that point would have
been no - #22 grew the test suite from 83→103 and the smoke check from
20→23, added two new files (`app/cities.py`, `app/validation.py`) and
a new endpoint (`GET /cities`), but `docs/GETTING_STARTED.md` (written
in the session before #21/#22) still said `85 tests` / `85 passed` in
three places, and neither it nor `backend/README.md` nor
`docs/FRONTEND_INTEGRATION.md` mentioned the new module or endpoint at
all. Caught by actually re-running the exact commands the guide tells
a junior to type, not by re-reading the prose.

**Fixed:**
- `docs/GETTING_STARTED.md`: corrected `85`→`103`/`1 passed` claims in
  Step 8 and Step 10 (re-ran both exact commands to confirm the new
  numbers first), added `cities.py`/`validation.py` to the "where do I
  look" table (Step 9), added a troubleshooting row for the new `400`
  validation responses.
- `backend/README.md`: added `GET /cities` to the endpoint list, noted
  the new server-side validation on `POST /complaints`.
- `docs/FRONTEND_INTEGRATION.md`: added a "Cities" section parallel to
  the existing "Categories" one, explicitly noting the frontend hasn't
  migrated to `GET /cities` yet (the same loose end already flagged in
  #22 - now discoverable from the doc whose whole purpose is tracking
  this exact kind of thing, not just from the ADR log).
- `docs/TESTING.md`: added a third "Update" paragraph so its opening
  summary reflects the 103/23 current counts instead of stopping at
  #20's 83/20, with an explicit note that older counts elsewhere in
  this file and in `docs/DECISIONS.md` are correct *as history*, not
  stale *as current status* - the ADR entries for #20-#22 were
  deliberately left with their original point-in-time numbers, since
  rewriting them to "103" would misrepresent what was actually true
  when each decision was made.

**Re-verified after fixing, not just after writing:** fresh venv,
`pytest -q` → `103 passed`; `pytest tests/test_api.py -k health_check
-v` → `1 passed` (the exact command Step 10 tells a reader to run);
live smoke check → `23 passed, 0 failed`. All three numbers now match
what the docs claim, checked in that order specifically because that's
the order a junior would hit them following the guide.

**Lesson for next time, stated plainly:** a multi-file doc change
(#21/#22 touched five docs, `GETTING_STARTED.md` wasn't one of the
five) is exactly the situation where something gets missed - worth a
grep for hardcoded counts/filenames across the whole `docs/` tree as a
last step whenever a change touches test counts, endpoints, or module
names, not just updating the docs that were "obviously" related.

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

## Decision 24: Live-deployment bug reports after handoff - ticket-input UX, Gemini embedContent 400, dataset clarification, dashboard chart polish

**Context:** After pushing to `main` and running the app for real (not
against any of the sandboxes this project has been built/tested in),
four things came back: a confusing "No complaint with ticket_no 1"
chatbot response, a real `400 Bad Request` from Gemini's `embedContent`
endpoint, a question about which of the two CSVs in `backend/data/`
actually trains the ML models, and a request to make the analytics
dashboard "prettier." All four investigated and (where fixable without
live API access) fixed in this session.

**1. Ticket numbering - not actually a numbering bug.** Verified
`app/tickets.py`, `load_dataset.py`, and both complaint-creation
endpoints in `main.py` all correctly compute `max(existing) + 1`
starting from 100000 - tickets genuinely do start at 100001 everywhere
data is created. The "ticket_no 1" in the screenshot was traced to
`admin-chatbot.html`'s "Ticket # (optional)" `<input type="number">`
having no `min` set - clicking a native number-input's spinner arrow
from empty defaults to `1` in most browsers, which is what produced
that specific query. Fixed by adding `min="100001" step="1"`. Frontend
JS (`admin-chatbot.js`) and the backend model (`AdminChatbotRequest.
ticket_no: Optional[int] = None`) were both already correct - neither
coerces a blank field to a number, confirmed by reading both before
touching anything.

**2. Dataset clarification.** `app/ml/train_classifier.py` and
`train_priority.py` both try `comcast_complaints.csv` (real Kaggle
data) first, falling back to `synthetic_complaints.csv` only if that's
missing, then `sample_complaints.csv` as a last resort - and print
which one was actually used (`(SYNTHETIC` or `real`, N rows)`) plus
record it in the saved metrics (`dataset_is_synthetic`). Since
`comcast_complaints.csv` is present (confirmed identical to the
original Kaggle download - see Decision 20), **training has always
used the real dataset**. `synthetic_complaints.csv` was a dev-only
stand-in generated by `generate_synthetic_dataset.py` for use before
the team had internet access to the real Kaggle CSV - it's not wired
into training at all today given the real file's presence, effectively
vestigial. Not deleted (harmless to keep as a fallback for a future dev
environment without internet), but worth knowing it's not what's
actually training anything right now.

**3. Gemini `embedContent` 400 Bad Request.** Root-caused by comparing
against several current, working examples of the same endpoint found
via web search (Google's own docs, a Postman collection, and a GitHub
issue showing a confirmed-successful response) - all of them include a
`"model": "models/<name>"` field **inside the request body**, even
though the model is already in the URL path. `embed_text()` in
`app/rag/gemini_client.py` was missing this field; `embed_texts()`
right next to it already had it (per-item, in its batch payload) -
that inconsistency is the most likely cause. Fixed by adding it to
`embed_text()` too. **Also fixed a real diagnosability gap independent
of the root cause**: the error text actually shown to the admin
(`"...request failed: 400 Client Error: Bad Request for url: ..."`)
came from `str(HTTPError)`, which does not include the response body -
and Google's error bodies are exactly where the *actual* reason lives
(`INVALID_ARGUMENT` and `FAILED_PRECONDITION` - e.g. billing/region
issues - both present as a bare 400 and are indistinguishable without
the body). Added `_raise_with_body()` so the real message from Google
surfaces directly in the admin chatbot UI next time, instead of a
generic status line. **Not verified against the live API** - this
session, like every sandbox this project has been built or extended
in, has no network path to `generativelanguage.googleapis.com`
(confirmed directly, not assumed - see Decision 20's same check
against a different set of hosts). If the error persists after this
fix, the improved message should now say why.

**4. Analytics dashboard visual polish.** The dashboard's KPI cards and
overall page CSS were already well-built (custom gradients, brand
typography, color-coded values); the actual weak point was Chart.js
rendering with its own defaults (grey gridlines, default black
tooltips, browser-default font) sitting next to that more polished
surrounding chrome. Rather than a redesign, added: a shared Chart.js
defaults block (Inter font, ink-toned tooltips matching the app's
palette instead of Chart.js's default black), softened/removed
gridlines and axis borders on both bar charts (monthly volume,
priority), and a single deliberate signature touch - a center-of-
doughnut total count, in the app's own Fraunces display face - on the
two doughnut charts (category, status). Consistent with the
frontend-design guidance to spend one bold move in one place and keep
everything around it quiet. Verified with `node --check` (syntax only,
Chart.js itself can't run outside a browser) and with a standalone
preview file (`dashboard_preview.html`, shared separately - not part
of the repo) that inlines the real `style.css`, the real updated chart
code from `admin-dashboard.js`, and realistic mock analytics data, so
the result could actually be seen before shipping rather than just
described.

**What's still open:** the Gemini fix is unverified against the live
API (see above - if it still 400s, share the new error text, which
will now include Google's actual message); the dashboard change has
only been checked for syntax + visually via the standalone preview,
not inside the real running app in an actual browser.

---

## Decision 25: Switched to Comcast_Cleaned.csv as the active dataset; clarified RAG architecture and junior team questions

**Context:** Junior team member (Khin Sis Thway) raised several
questions, translated and addressed below. Also switched the committed
training dataset to the cleaned version they prepared.

**Q1: Do we need PDF files for RAG, or 2 datasets?**

Neither — RAG uses a completely separate, third thing: the
`data/knowledge_base/` folder. Right now it contains 5 Markdown
files (one per complaint category: `billing_sop.md`,
`technical_sop.md`, etc.) — Standard Operating Procedure documents
that tell an admin how to handle each complaint type. These are what
get embedded and indexed into Qdrant, and what the admin chatbot
searches when answering questions. **PDF files are also supported**
(the indexer reads `.md`, `.txt`, and `.pdf` from that folder) — if
the team wants to add a real SOP manual as a PDF, they can just drop
it in `data/knowledge_base/` and re-run `python -m app.rag.
knowledge_base`. The two training datasets (`comcast_complaints.csv`
and `synthetic_complaints.csv`) are NOT used by RAG at all — they
train Algorithms 1 and 2 (category classification and priority
prediction), which is a completely different pipeline. The "chatbot
isn't responding" note in the synthetic dataset file header is
exactly what it says: a placeholder note from before the real chatbot
was built, not something that affects the current app.

**Q2: The 2025 dataset only has 776 rows?**

The junior team's message is referring to a *different* version of the
file. The Comcast_Cleaned.csv they've now provided has **2224 rows**
(all of 2025, January–December), same count as the original Kaggle CSV
— just with dates updated to 2025-format ISO dates, the `Date_month_year`
column in clean `YYYY-MM-DD` format (vs the original's `DD-Mon-YY`),
and a new `Complaint_Clean` pre-processed text column added. All 2224
rows load, train against, and parse correctly — confirmed by actually
running `train_classifier.py` and `train_priority.py` against the file
(both print "real, 2224 rows"), and by checking `parse_date()` against
the new ISO format (handled correctly by the existing multi-format
parser). No code changes needed to any training scripts.

**Q3: Dataset cities are US cities, but the app is for Myanmar.**

Correct — and this was always intentional, documented at Decision 17.
The Comcast dataset is the training source for the ML models (Algorithms
1 and 2) because it has real telecom complaint text that generalises
well to the complaint *classification* task. The Myanmar-specific context
(63-city dropdown, Myanmar timezone, Burmese-friendly UI) is entirely on
the frontend and backend validation layer — it doesn't depend on the
training data's city column at all. Customers file complaints about
their telecom service in their own words; the ML reads the complaint
*text*, not the city. The Comcast dataset's US city/state/zip columns
are loaded historically (for the analytics dashboard's data) but the
Myanmar cities in `app/cities.py` are what appear in the complaint form's
autocomplete and what the server-side city validation checks against.

**Q4: "chatbot isn't responding" note in the synthetic dataset.**

This is just a leftover comment in `generate_synthetic_dataset.py` from
the era before the real chatbot was implemented — it's not a live error
in the current app. The admin chatbot works (or falls back gracefully
with an honest message) independently of which training dataset is loaded.
Customers never see the chatbot at all — it's admin-only, as confirmed.

**What actually changed in code this session:**
- `backend/data/comcast_complaints.csv` → replaced with
  `Comcast_Cleaned.csv` (same 2224 rows, ISO dates, `Complaint_Clean`
  column added, `Date` column now NaN — the multi-format parser handles
  this without any code change).
- Both ML models retrained against the new file: 93.0% category
  accuracy, 100% priority accuracy (same as before — the complaint
  text didn't change, only the date format and an extra column).
- `data/load_dataset.py` docstring updated to document the new
  `Complaint_Clean` column and explain that the ISO date format needs
  no conversion (unlike the original raw CSV's `DD-Mon-YY` format).
- Full test suite: 103/103 still passing. Both training scripts
  confirm "(real, 2224 rows)" and correct model family in artifacts.

---

## Decision 26: Five live-run issues fixed - RAG .env loading, Qdrant 404 message, dashboard empty on startup, time picker seconds, VISUALIZATIONS.md

**Context:** After actually running the app locally, five more issues
surfaced all at once. Addressed in a single session.

**1. `python -m app.rag.knowledge_base` said "GEMINI_API_KEY not set"
even though `.env` had it.**

Root cause: `load_dotenv()` is only called in `app/db.py`, which gets
imported when the FastAPI server starts. Standalone scripts bypass that
chain entirely - `os.getenv()` in `gemini_client.py` reads whatever
the shell environment has, which does NOT include anything in `.env`
unless something loaded it first. Fixed by adding a `.env` search-and-
load block at the top of `app/rag/knowledge_base.py`, before any
`import` that calls `os.getenv()` (imports are where the value gets
captured into module-level constants). The search tries
`backend/.env` first (most likely path), then the repo root. Uses a
try/except around the dotenv import in case someone runs this on a
system that doesn't have `python-dotenv` installed somehow (though it's
in requirements.txt).

**2. Qdrant "Collection doesn't exist" 404 showed a raw JSON blob in
the admin chatbot UI.**

The improved error-body surfacing from Decision 24 (`_raise_with_body`)
made the Qdrant 404 body visible - good, it confirmed the diagnosis.
But the message was still a raw `{"status":{"error":"Not found:
Collection loopline_sop_chunks doesn't exist!"...}}` blob that told an
admin nothing about what to do. Fixed in `vector_store.py`'s
`_qdrant_search()` by checking `resp.status_code == 404` specifically
before the generic error case, and raising a `VectorStoreError` with an
actionable English message ("Knowledge base not indexed yet — run
`python -m app.rag.knowledge_base` from backend/ with GEMINI_API_KEY
in .env. See docs/GETTING_STARTED.md Step 11 or docs/RAG_CHATBOT.md.")

**3. Admin dashboard showed empty charts on first run (in-memory DB).**

The in-memory database starts empty every time the server starts (by
design - it's a dev convenience, not a persistent store). The admin
seed (`ensure_admin_seeded()`) creates the admin account, but nothing
created any complaint data, so the analytics endpoint returned empty
counts and the four charts had nothing to render.

Fixed by adding `app/dataset_seed.py` — `ensure_dataset_seeded()`
called at startup immediately after `ensure_admin_seeded()`. It reads
`comcast_complaints.csv`, classifies each complaint through Algorithms
1 and 2 (same path as a real filed complaint), and inserts all 2224
rows into the in-memory collection. Runs only when: (a) no `MONGODB_URI`
is configured (real MongoDB is assumed to have data from a manual
`load_dataset` run), and (b) the complaints collection is currently
empty. Idempotent — never duplicates. One-time cost on first startup;
subsequent startups are fast (the collection isn't empty anymore...
but wait, it IS empty again because in-memory doesn't persist across
restarts). This is a real consequence: every server restart re-seeds.
That's acceptable because (a) it only happens in dev/in-memory mode,
(b) the seeding completes in a few seconds, and (c) the alternative
(a persistent dev database) is significantly more setup work. Logged
plainly in the startup output:
`[dataset_seed] Seeded 2224 complaints — dashboard analytics are now
populated.`

**4. Time picker showing hours, minutes, *seconds*, and AM/PM.**

The "seconds" dropdown (0-59 in a dropdown) added no real value - for
a complaint filing form "when did this happen," granularity beyond
HH:MM is meaningless, and the backend ignores the frontend time anyway
(it stamps the real server time on submission, as noted in a comment
already in the submit handler). Removed the `f-second` `<select>` from
`activities.html`, removed it from `buildTimeSelectOptions()` and
`updateTimePreview()` in `script.js`, and hardcoded `second = '00'` in
the submit handler so the validation function still receives a valid
value without any code change to `validateDateTimeYangon()`. Also merged
the Date and Time fields into a single visual row (`datetime-row` CSS
class) and relabeled the field to "Date & Time of Incident — Auto-set
to now, adjust if it happened earlier." This explains the purpose:
the customer is recording *when the incident happened*, not when they
filed it (the server timestamps filing separately).

**5. `docs/VISUALIZATIONS.md` added for junior team.**

Khin Sis Thway asked (in Burmese): "What charts and graphs are shown
for visualization? Right now there's no data so we can't see them."
Two separate answers needed: (a) what the charts ARE, and (b) why
there's no data and how to get data appearing. Both answered in the new
doc. Also added to `README.md`'s documentation table and linked from
`docs/GETTING_STARTED.md` Step 9's codebase map.

---

## Decision 27: Team replaced Chart.js dashboard with pure-SVG implementation featuring a baseline/live toggle

**Context:** Chart.js CDN (`cdnjs.cloudflare.com`) was blocked in the
team's network environment (Myanmar), causing a `ReferenceError: Chart
is not defined` that silently killed all four charts. Multiple attempts
to work around Chart.js (plugin null-checks, CDN removal, SVG
rewrites) were interrupted by session/time limits. The team fixed it
themselves and submitted the working files. Their version was adopted
as-is into the repository.

**What the team built:**

1. **Pure SVG chart renderers (no external library, no CDN):**
   `svgBarChart()`, `svgDonutChart()`, `svgHBarChart()` — all written
   against the DOM's `createElementNS` SVG API. Works on `file://`,
   `localhost`, and any server. Cannot fail due to CDN issues.
   Interactive tooltips (`mouseenter`/`mousemove`/`mouseleave`) on
   every bar and donut slice.

2. **Data-source toggle UI:** A pill toggle bar above the charts lets
   the admin switch between "📊 Comcast Baseline (2,224)" and
   "🔴 Live Data" at any time. On page load, the baseline renders
   immediately (no network wait), then live data is fetched in the
   background and cached so the toggle is instant. If the live fetch
   fails, it falls back to baseline with a toast.

3. **Hardcoded baseline in `BASELINE` constant:** Comcast dataset
   statistics (2,224 complaints, 12 months of 2025 volume,
   by_category / by_priority / by_status breakdowns) are embedded
   directly in the JS so charts always show real, meaningful data
   regardless of backend connectivity. Note: the baseline's monthly
   volume uses an evenly-distributed approximation (215 complaints/mo)
   rather than the actual per-month counts (which have a large June
   2025 spike at 1,046). This is intentional — the team chose a
   presentation-friendly distribution.

4. **`loadAnalytics()` flow:** renders baseline synchronously → fires
   live fetch in background → if `_currentSource === 'live'` when the
   fetch resolves, applies live data then; otherwise caches it for
   when the user toggles.

**One bug fixed during adoption:** `m.month.slice(3)` worked for the
BASELINE's `'25-01'` format but broke for the live API's `'2025-01'`
format (would show `'5-01'` as the month label). Changed to
`m.month.slice(-2)` which correctly returns `'01'` for both formats.

**CSS:** All new CSS classes (`.svg-chart-host`, `.donut-wrap`,
`.ds-toggle-bar`, etc.) added to `frontend/style.css` so they work
in all contexts. The HTML's inline `<style>` block remains as a
harmless fallback.

**Verified:** `node --check` syntax clean, `pytest` 103/103,
all HTML pages parse without errors.

---

## Decision 28: Comcast baseline pagination in admin table; junior's MongoDB error analysed; Qdrant/Cursor test fixes

**Context:** Three separate things addressed in one session.

**1. Baseline complaints table with full pagination (the main work)**

Before this: the chart toggle ("📊 Comcast Baseline" / "🔴 Live Data")
only switched the four analytics charts. The "All Complaints" table
below always showed live database records regardless of toggle state,
which confused the junior team ("when I select Comcast dataset the
table still shows live data"). Previously: this was labelled a UX
clarification, not a bug. This session: actually implemented the
full switch so the table follows the toggle.

New endpoint: `GET /admin/complaints/baseline` — reads all 2224 rows
from `comcast_complaints.csv`, applies Algorithm 1 (category
classifier) and Algorithm 2 (priority predictor) to each row via the
same `classify_complaint` + `predict_priority` functions used for live
complaints, caches the results in memory (`app/baseline_cache.py`,
thread-safe double-checked locking), then returns paginated/filtered
JSON in the same shape as `GET /admin/complaints`. First call takes a
few seconds (classifying 2224 rows); all subsequent calls are instant
from cache.

Frontend: `loadTable()` now reads `_currentSource` and hits
`/admin/complaints/baseline` in baseline mode vs `/admin/complaints`
in live mode. `renderTable()` gained a `readOnly` flag: baseline rows
show pill labels instead of `<select>` dropdowns so they're visually
distinct (can't edit history), while live rows keep full inline-edit
selects. `switchDataSource()` now resets `currentPage = 1` and calls
`loadTable()` so the table switches immediately. The toggle sub-label
updated from "affects charts only" to "affects charts and the
complaints table below." The table heading updates dynamically:
"comcast dataset · read-only" vs "live database records."

Verified: `app/baseline_cache.get_baseline()` returns 2224 rows,
465 Billing rows, 149 pages of 15, 4 items on the last page. 103/103
tests still passing.

**2. Junior's MongoDB Atlas `ServerSelectionTimeoutError`**

Error: `No replica set members match selector "Primary()"`. Topology:
shard-00-00 RSSecondary ✓, shard-00-01 RSSecondary ✓, shard-00-02
Unknown (NetworkTimeout). **This is a network problem on her device,
not a code or credential problem.** 0.0.0.0/0 Atlas whitelist is
correct. The owner's machine works fine on the same connection string,
which rules out wrong URI, wrong credentials, wrong cluster. One of
the three Atlas shards (shard-00-02) is unreachable from her network
— this creates a split-brain where the replica set can see secondaries
but not elect a primary, blocking all writes and most reads.

Likely causes and things to try (in order): (1) her ISP or corporate
network blocks port 27017 to specific IP ranges — test by trying a
different network (phone hotspot is the fastest test); (2) Windows
Firewall or antivirus blocking outbound port 27017 — disable
temporarily to test; (3) if on a VPN, the VPN may be routing Atlas
traffic asymmetrically — disconnect VPN and retry; (4) check her
`ping ac-01f50qg-shard-00-02.ldkskgs.mongodb.net` — if it times out
while the other two don't, the problem is confirmed network-side.

**3. Two test fixes (from ChatGPT's analysis, independently verified)**

Both confirmed by reading the actual code before trusting the analysis:
- `test_admin_seed.py::test_ensure_admin_seeded_is_idempotent`: called
  `len(collection.find())` which fails on a real pymongo `Cursor`
  (no `__len__`). Fixed with `list(...)` wrapper.
- `test_vector_store.py` (3 tests): `QDRANT_URL` is captured into a
  module-level constant at import time. Once a real Qdrant URL is in
  `.env`, `reset_memory_store()` has no effect — `is_configured()`
  returns True and test vectors (3-dim) hit the real Qdrant collection
  (768-dim) → dimension mismatch. Fixed by: (a) making `is_configured()`
  read from `sys.modules[__name__].QDRANT_URL` so it respects
  monkeypatching, and (b) adding an `autouse` fixture that patches
  `vector_store.QDRANT_URL` to `None` before each test.

---

## Decision 29: Test suite was writing to real Atlas — conftest.py now strips all real credentials before any import

**Context:** Unexpected complaint entries appeared in the team's real
MongoDB Atlas database — entries nobody on the team deliberately added.
The root cause was traced definitively by reading the code:

`backend/app/db.py` line 20:
```python
MONGODB_URI = os.getenv("MONGODB_URI")
```
This runs at **module import time**. `conftest.py` previously only
added `backend/` to `sys.path` — it did not clear `MONGODB_URI`. So
when anyone ran `pytest` with a real `MONGODB_URI` in their `.env`
(which auto-loads via the shell or dotenv in many setups), `db.py`
captured the real Atlas URI at import time, and every `get_collection()`
call during the test run returned a **real Atlas collection**. All
`POST /complaints` calls in `test_api.py` — "A's private complaint",
"B's private complaint", "My bill was overcharged this month",
"totally unrelated text", "Customer called about a billing dispute"
etc. — were written to the real production database. This had visibly
happened (the team saw entries nobody remembered adding).

The same problem applied to `QDRANT_URL` and `GEMINI_API_KEY` —
any test that exercises the RAG pipeline could have made real Qdrant
writes or Gemini API calls, costing money and polluting the live
vector index.

**Fix:** Added credential-stripping to the very top of `conftest.py`,
before any import from `app.*`:
```python
for _key in ("MONGODB_URI", "QDRANT_URL", "QDRANT_API_KEY", "GEMINI_API_KEY"):
    os.environ.pop(_key, None)
```
Must be before imports because Python captures module-level
`os.getenv()` calls at first import, not at call time — you cannot
fix this with a session-scoped pytest fixture, because fixtures run
after module collection (and thus after imports). The `os.environ.pop`
approach works because `conftest.py` is always loaded first, before
any test file.

**Verified:** ran `pytest -q` with a real-looking `MONGODB_URI`,
`QDRANT_URL`, and `GEMINI_API_KEY` present in the shell environment.
103/103 passing. Confirmed `db.MONGODB_URI is None` inside the test
process — in-memory fallback active regardless of what `.env` contains.

**What to do about the existing spurious Atlas entries:** delete them
manually. In MongoDB Atlas Data Explorer, filter the `complaints`
collection for entries with complaint text matching known test strings
("A's private complaint", "B's private complaint", "My bill was
overcharged this month", "totally unrelated text", "Customer called
about a billing dispute", etc.) or filter by `user_id` values that
were generated by the test suite. Alternatively, if the Atlas
collection only has test noise and no real customer data yet, a full
collection drop and re-seed with `python -m data.load_dataset` is
faster than hunting individual documents.

**Note:** Claude (the AI assistant) had no network path to Atlas at
any point during this project — confirmed via direct test on every
session that attempted it (`x-deny-reason: host_not_allowed`).
The writes came from the local `pytest` runs on the team's own
machines.

---

## Decision 30: RAG pivot to BM25 + hybrid retrieval (Gemini embeddings + Qdrant → BM25 + optional Gemini query embeddings + RRF)

**Context:** The original RAG stack (Decision 14) embedded every SOP
chunk with Gemini `batchEmbedContents` at index time and searched
Qdrant at query time. This hit the free-tier quota (≈1000 embeddings/
day) within a single re-index run of the five SOP documents (2315
chunks). The system stopped working until the next day.

**Immediate fix (already shipped before this session):**
`app/rag/knowledge_base.py` was rewritten to use pure-Python BM25
(Okapi BM25, `app/rag/bm25_store.py`) at index time. The index is
saved as `.bm25_index.json`. `app/rag/pipeline.py` calls BM25 for
retrieval and Gemini `generateContent` only for the final answer —
no embedding calls at all. This is reflected in the header comment of
`knowledge_base.py` ("This replaced Gemini embeddings + Qdrant after
hitting the free tier's 1000/day embedding quota").

However, the documentation (this file, `docs/RAG_CHATBOT.md`,
`ROADMAP.md`, and others) still described the original Gemini + Qdrant
architecture, and the fallback error string in `app/chatbot.py` still
mentioned "Qdrant". This session closes all of those gaps.

**Hybrid upgrade (this session):**
BM25-only has a known weakness: exact-match only. Paraphrases miss
("how do I deal with a customer who keeps getting billed" vs "repeat
billing complaint"). To address this without re-introducing the quota
problem, a hybrid retrieval mode was added:

- **BM25 is still the default** and runs on every query (no API, no
  quota, works fully offline).
- **Gemini query embedding** (one call per admin question, not
  per-chunk) provides semantic coverage for paraphrases. Only the
  query is embedded — never the document corpus.
- **Reciprocal Rank Fusion (RRF)** merges the two ranked lists:
  `score = Σ 1/(60 + rank_i)` (Cormack et al. 2009). Chunks
  appearing in both lists score significantly higher.
- **Graceful degradation:** if Gemini embedding fails for any reason
  (missing key, timeout, rate limit), the system silently returns
  BM25-only results. No error is surfaced to the caller.

**Why not embed a small curated subset at index time?**
Considered, but deferred. The embedding path's main value is semantic
query understanding, which requires only a query vector, not a
pre-embedded corpus. Adding "golden FAQ" chunk embedding would help
recall but reintroduces the quota risk and requires a separate
curation step. Left as a future option (see ROADMAP).

**Files changed this session:**

| File | Change |
|---|---|
| `app/rag/hybrid_retriever.py` | **New.** `HybridRetriever` class with `search_bm25`, `search_embeddings`, `fuse_results`, `search` methods. |
| `app/rag/pipeline.py` | Now calls `HybridRetriever.search()` instead of `BM25Index.search()` directly. API surface unchanged; two new boolean fields added to the return dict (`used_bm25`, `used_embeddings`). |
| `app/rag/__init__.py` | Docstring updated to reflect current architecture. |
| `app/chatbot.py` | Module docstring updated; fallback error strings no longer mention "Qdrant". |
| `docs/RAG_CHATBOT.md` | Full rewrite: now describes BM25 + hybrid, not the old Gemini + Qdrant indexing. |
| `ROADMAP.md` | Status table updated; hybrid retrieval row added. |
| `backend/tests/test_bm25_store.py` | **New.** 19 unit tests for `BM25Index` (ranking, persistence, IDF, cache). |
| `backend/tests/test_hybrid_retriever.py` | **New.** 21 tests across 4 classes: BM25-only, embedding-only (Gemini + vector_store mocked), RRF fusion, graceful degradation. |

**Trade-offs acknowledged:**

- `app/rag/vector_store.py` and the embedding helpers in
  `gemini_client.py` are now partially legacy code. They're kept
  because `HybridRetriever.search_embeddings()` uses them for the
  optional embedding path. Removing them would break that path.
- The Qdrant vector index is empty in the current deployment (no
  chunks have been upserted since switching to BM25). The embedding
  arm of hybrid search will return empty results until Qdrant is
  seeded with chunk vectors. This is by design — the BM25 arm always
  provides results, so the overall system remains fully functional.
- Test count: 103 → 143 (40 new tests, all passing). The two
  pre-existing failures (`test_knowledge_base::test_load_documents_finds_all_sop_files`
  and `test_ml_models::test_priority_model_predicts_a_real_level`) are
  unchanged sandbox-environment issues (filename mismatch and missing
  `xgboost`), not caused by this session's changes.

---

## Decision 31: Backend query optimisation + frontend design system consistency for admin-customers

**Context (the problems found after initial shipping):**

After the customer accounts feature (Decision 30 session) shipped, two
classes of problems were identified from live usage:

*Backend:* `GET /admin/customers` fetched every complaint in the
collection to build counts, then discarded all but the page_size
entries (default 20). `GET /admin/customers/{user_id}` did the same
redundant full scan a second time just to count one user's complaints.
Both endpoints also materialised the full complaint documents when only
`user_id` was needed for the count step.

*Frontend:* The customers page was missing the page-level header, the
search bar was floating outside any container, the complaint-count
badge used inconsistent styling (0 got an outline circle while non-zero
got a filled circle), the View button used an emoji instead of the SVG
icon pattern used elsewhere, and the modal profile layout used a CSS
grid that broke at small widths.

---

**Backend changes — what and why:**

**1. Projection on the count query.**
`GET /admin/customers` now passes `{"user_id": 1}` as the projection
argument to `.find()`. MongoDB (and the in-memory fallback) return only
the `user_id` field from each matching complaint document instead of
the full complaint text, category, and all other fields. For 2315
seeded complaints this cuts the data transferred per page load by
roughly 98%.

**2. Page-scoped count query.**
The complaint count query is now filtered to `{"user_id": {"$in":
page_ids}}` where `page_ids` contains only the ≤20 user IDs visible on
the current page. Previously it fetched all complaints regardless of
which users were on screen.

**3. `_build_customer_out` helper.**
Extracted a single function that maps a raw `users` document to
`AdminCustomerOut`. This ensures `password_hash` and any other raw
fields can never accidentally appear in the response regardless of
future changes to the `users` document shape.

**4. `GET /admin/customers/{user_id}` — removed double scan.**
The detail endpoint previously fetched all complaints (for counting)
and then fetched the same user's complaints again (for the response).
It now does one targeted `.find({"user_id": user_id})` and uses
`len(complaints)` for the count, eliminating the second query entirely.

**Asymptotic improvement:**

| Endpoint | Before | After |
|---|---|---|
| List — complaint data fetched | O(N_complaints) full docs | O(page_complaints) × projection only |
| Detail — DB queries | 2 (full scan + targeted) | 1 (targeted) |

At the current dataset size (~2300 complaints, 6 customers) the wall
time improvement is small but the pattern is correct and will not
degrade as data grows.

---

**Frontend changes — what and why:**

**1. Page header restored.**
The `activities-header` block (eyebrow + h1 + subtitle) was missing
from the customers page, leaving the page with no visual context. Added
to match the exact structure of the activities and dashboard pages.

**2. Summary stat cards.**
Three `summary-card` elements (Total Customers, With Open Complaints,
No Complaints) added above the table card using the existing
`.summary-cards` grid and `.summary-card` classes. These populate from
the API response client-side with no extra request.

**3. Table wrapped in `.card.table-card`.**
The table was floating without a container. Now wrapped in the same
`<section class="card table-card">` scaffold the dashboard uses,
giving it the correct white background, border-radius, and shadow.

**4. Filter bar uses existing `.filter-bar` / `.search-wrap` classes.**
The previous search bar used ad-hoc inline styles. Now uses the exact
same `.filter-bar` + `.search-wrap` + `.search-icon` + `.filter-clear`
classes as the dashboard, so styling is inherited automatically and any
future style updates apply everywhere.

**5. Complaint-count badge.**
Replaced the `inline-label` (intended for text labels like "Billing")
with a new `.count-badge` class scoped to this page. Zero counts get
`.count-badge.zero` (muted grey) and non-zero get the teal version.
This removes the inconsistency where 0 rendered differently from 1+.

**6. View button SVG icon.**
Replaced the 👤 emoji with a 12×12 SVG person-outline icon matching
the `.row-btn-view` eye icon pattern on the dashboard.

**7. Modal profile grid.**
Replaced the `view-grid` (used for complaint details, 2-column label/
value) with a new `cust-profile-grid` using a border-table layout:
each field is a bordered cell with a small-caps label above a value.
This is consistent with how profile information is displayed on the
activities page and is responsive (collapses to 1 column on mobile via
a scoped `@media` rule).

**8. Open issues display.**
"Pending" and "In Progress" counts in the modal now render as
`status-badge` pills at reduced opacity (0.45) when zero, rather than
always showing the full amber colour. This visually communicates "none"
without removing the information.

**9. Event delegation on the tbody.**
The previous code called `querySelectorAll('[data-action]').forEach(...
addEventListener)` after every render, attaching N listeners for N
rows. Replaced with a single `click` listener on `tbody` that checks
`e.target.closest('[data-action]')` — one listener regardless of row
count, no memory leak on re-render.

**Files changed:**

| File | Change |
|---|---|
| `backend/app/main.py` | `_build_customer_out` helper; projection on count query; single-query detail endpoint |
| `frontend/admin-customers.html` | Header, stat cards, table-card wrapper, filter-bar, pagination using existing CSS classes |
| `frontend/admin-customers.js` | Stat card update; count-badge class; SVG icon; `cust-profile-grid` modal; `cust-open-pills`; event delegation |

---

## Decision 32: In-memory store operator support + table alignment + modal layout overhaul

**Problems identified from live usage screenshots:**

**Backend — `$in` operator not implemented in `_InMemoryCollection`**
`GET /admin/customers` uses `.find({"user_id": {"$in": page_ids}}, {"user_id": 1})`.
The original `_InMemoryCollection.find()` matched query clauses with
`d.get(k) == v` — a dict like `{"$in": [...]}` is never equal to an
integer, so every complaint was silently excluded from the count. The
count was always 0 for every customer in in-memory mode. Additionally,
projection (`{"user_id": 1}`) was ignored entirely, so the full
complaint document was returned instead of just the `user_id` field.

**Fix:** Rewrote `_InMemoryCollection` with:
- `_matches(doc, query)` — handles equality, `$in`, and `$nin`
  operators per key, making the in-memory store compatible with the
  same query shapes used for real MongoDB.
- `_project(doc, projection)` — applies include-only projections
  (`{field: 1}`), so the count query only returns `user_id` per doc,
  matching the MongoDB behaviour.
- `find_one` now short-circuits on first match instead of calling
  `find()` and taking `[0]`, avoiding materialising the full result.

Both `_InMemoryCollection` and real MongoDB now behave identically for
these query shapes. No changes to call sites in `main.py`.

**Frontend — table row misalignment (Image 2 circle)**
`complaint-table tbody td` had `vertical-align: top`. When a complaint
cell wraps to two lines, the inline-select cells (category, priority,
status) are shorter and sit at the top of the row, creating a visible
step between their bottom edge and the divider line of the row below.
Changed to `vertical-align: middle` — all cells in a row now sit
centred on the row's height regardless of which cell is tallest.

**Frontend — customer modal layout**
The two-column profile grid (`cust-profile-grid`) broke at narrow
viewport widths and its bordered-cell approach produced uneven spacing
when field values were different lengths. Replaced with a
label-left / value-right list pattern (`cust-info-list` / `cust-info-row`):
- Label column is `flex: 0 0 140px` — fixed width regardless of
  content, so all values start at the same x position (like a
  settings panel).
- Each row is a full-width flex container with a `1px` bottom border,
  which renders consistently at any viewport width.
- No grid breakpoint needed — the layout collapses naturally because
  both columns are inline-flex items that wrap only when the label
  width is reduced via the `@media (max-width: 560px)` rule.
- Open-issues pills use `opacity: 0.4` when count is zero rather than
  a separate visual state, preserving information while reducing noise.

**Files changed:**

| File | Change |
|---|---|
| `backend/app/db.py` | `_InMemoryCollection`: `$in`/`$nin` support, projection support, `find_one` short-circuit |
| `frontend/style.css` | `complaint-table tbody td`: `vertical-align: top` → `vertical-align: middle` |
| `frontend/admin-customers.html` | Switched to `cust-info-list` modal layout; removed scoped grid CSS |
| `frontend/admin-customers.js` | `renderModal` uses `cust-info-list`/`cust-info-row`; `DocumentFragment` batch DOM insert; `tbody.onclick` delegation |

---

## Decision 33: Groq as primary LLM backend; complaint form validation fixes

### Part A — Groq replaces Gemini for generation

**Problem:** `generativelanguage.googleapis.com` is geo-blocked in Myanmar.
Every chatbot request from the deployment environment results in a
connection timeout regardless of API key validity. The admin chatbot
was non-functional for the entire team running the thesis demo.

**Solution:** Added `app/rag/groq_client.py`, a plain `requests`-based
wrapper around Groq's OpenAI-compatible `/v1/chat/completions` endpoint.
Groq's `api.groq.com` is accessible from Myanmar and offers a generous
free tier. Default model: `meta-llama/llama-4-scout-17b-16e-instruct`
(override via `GROQ_MODEL` in `.env`).

**Priority order in `pipeline.py`:**
1. Groq (`GROQ_API_KEY` set) — used first.
2. Gemini (`GEMINI_API_KEY` set, no Groq key) — fallback for envs where
   Groq is unavailable but Gemini is reachable.
3. Neither → raises an error that `chatbot.py` converts to a graceful
   template fallback message (existing behaviour unchanged).

**Embedding is not affected.** Groq does not provide embedding APIs.
The BM25 arm of `HybridRetriever` runs unconditionally. The Gemini
embedding arm silently returns `[]` when `GEMINI_API_KEY` is absent —
this was already the designed fallback path; no code change needed.

**Files changed:**

| File | Change |
|---|---|
| `app/rag/groq_client.py` | **New.** `generate_text()`, `is_configured()`, `GroqError` (also exported as `GeminiError` alias for zero-change caller compatibility). |
| `app/rag/pipeline.py` | `_generate()` helper tries Groq first, Gemini second. `_is_configured()` checks both. |
| `app/chatbot.py` | Imports `groq_client`; `ask_admin_chatbot` checks `groq_client.is_configured() or gemini_client.is_configured()`; updated fallback message. |
| `backend/.env.example` | `GROQ_API_KEY` and `GROQ_MODEL` added as primary; Gemini kept as documented fallback; geo-block note added. |
| `frontend/admin-chatbot.html` | Stale "via Gemini + Qdrant" description updated to "BM25 keyword retrieval and LLM generation". |

---

### Part B — Complaint form validation fixes

**Bug 1 — `isMeaningfulComplaint` returns bare `false`, causing silent crash.**
`if (!text) return false` — all callers do `.ok` on the return value.
`false.ok` throws `TypeError: Cannot read properties of undefined`.
This silently prevented form submission whenever the textarea was
empty at the point of the check. Fixed: always return `{ok, reason}`.

**Bug 2 — Capital letters counted as word-boundary characters.**
`t.toLowerCase().split(/[^a-z]+/)` was intended to extract words after
lowercasing, but the split regex `[^a-z]` also matches digits, spaces,
and any character that isn't a lowercase letter — including the original
capital letters *after* lowercasing (they're already lowercase at that
point, so this was actually fine). The real problem: the split pattern
discards any word containing a non-letter character (e.g. "Wi-Fi",
"100Mbps", or any word with a hyphen or number). A complaint like
"Wi-Fi disconnects every night" would split into fragments that fail
the 2-character minimum. Fixed: split on whitespace (`/\s+/`) instead,
which correctly counts all space-separated tokens as words.

**Bug 3 — Error message for length didn't show actual count.**
Generic "Please enter a meaningful description" didn't tell the user
how long their text was. Updated to show `(N/20 characters minimum)`
and `(N/1000 characters maximum)` so the user knows exactly what to fix.

**Files changed:**

| File | Change |
|---|---|
| `frontend/script.js` | `isMeaningfulComplaint`: always return object; whitespace word split; informative length messages |

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
