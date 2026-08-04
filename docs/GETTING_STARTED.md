# Getting started (for anyone new to Loopline)

This doc assumes nothing - not that you've used FastAPI before, not
that you know what a virtual environment is, not that you've touched
this codebase at all. If you already know your way around a Python
backend, `backend/README.md` is the faster reference version of most
of this. If you get stuck on anything below and the fix isn't obvious,
that's a gap in this doc, not a dumb question - ask, and whoever
answers should add it to the Troubleshooting section for the next
person.

## What this project actually does, in plain language

A customer types a complaint into a web page ("my bill is wrong",
"internet keeps dropping"). The backend automatically figures out
*what kind* of complaint it is (Billing, Technical, etc.) and *how
urgent* it is (Low/Medium/High), using two small machine learning
models trained on a real dataset of ~2,200 Comcast complaints. The
customer can track their complaint's status. An admin has a dashboard
to see everything, filter/search it, edit it by hand, see analytics,
and ask an AI chatbot questions grounded in the team's support
procedures. That's the whole product - everything below is just "how
do I get that running on my laptop and start changing it."

---

## Step 1: What you need installed

| Tool | Why | Check you have it |
|---|---|---|
| **Python 3.11 or 3.12** | Runs the backend | `python3 --version` (Windows: `python --version`) |
| **git** | Version control - see `docs/GIT_SETUP.md` for the team workflow | `git --version` |
| **A code editor** | VS Code is the common choice, but any editor works | - |
| **A web browser** | Runs the frontend - Chrome/Firefox/Edge, any modern one | - |

You do **not** need Node.js, Docker, MongoDB, or any API keys to get a
fully working version of this running - see Step 5.

**Don't have Python installed?**
- **Windows**: download from [python.org/downloads](https://www.python.org/downloads/) and run the
  installer. Important: tick **"Add python.exe to PATH"** on the first
  install screen, or the `python` command won't work afterward.
- **Mac**: download from the same link, or if you use
  [Homebrew](https://brew.sh): `brew install python@3.12`
- **Linux**: almost always already installed; if not,
  `sudo apt install python3 python3-venv` (Ubuntu/Debian) or your
  distro's equivalent.

After installing, close and reopen your terminal, then re-run
`python3 --version` (or `python --version` on Windows) to confirm it
worked - you should see something like `Python 3.12.4`.

**A note on terminal commands in this doc:** every code block below is
something you type into a terminal (Mac/Linux: Terminal app; Windows:
PowerShell, or the terminal built into VS Code - View → Terminal). One
line at a time, press Enter after each.

---

## Step 2: Get the code

**If your team is using shared Git already** (see `docs/GIT_SETUP.md`):
```bash
git clone https://github.com/<your-team>/loopline.git
cd loopline
```

**If you were handed a `.zip` file instead:** unzip it anywhere sensible
(e.g. your Desktop or a `projects` folder), then open a terminal and
`cd` into the folder it created:
```bash
cd path/to/loopline
```
Tip: on Mac/Windows you can usually type `cd ` (with a trailing space)
into the terminal, then drag the folder from Finder/Explorer into the
terminal window - it fills in the path for you.

**Confirm you're in the right place** - this should show `backend`,
`frontend`, and `docs` folders:
```bash
ls
```
(Windows PowerShell: `dir` works the same way.)

---

## Step 3: Set up the backend (Python environment)

Move into the backend folder - **everything in this step happens from
inside `backend/`**, not the top-level `loopline/` folder:
```bash
cd backend
```

### 3a. Create a virtual environment

A virtual environment ("venv") is a private, isolated copy of Python
just for this project, so the packages it needs don't clash with any
other Python project on your machine. Create one:
```bash
python3 -m venv venv
```
(Windows: `python -m venv venv`. Either way this creates a new `venv/`
folder - it's already excluded from Git via `.gitignore`, don't worry
about committing it.)

### 3b. Activate it

You have to do this **every time you open a new terminal** to work on
this project (it doesn't stay active across terminal sessions):

- **Mac/Linux**: `source venv/bin/activate`
- **Windows (PowerShell)**: `venv\Scripts\Activate.ps1`
- **Windows (Command Prompt)**: `venv\Scripts\activate.bat`

You'll know it worked because your terminal prompt now starts with
`(venv)`, like:
```
(venv) you@laptop backend %
```
If nothing changed, it didn't activate - re-read the command for your
OS above (this trips people up constantly, it's not just you).

**Windows PowerShell "running scripts is disabled" error?** Run this
once, then retry the activate command:
```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

### 3c. Install the dependencies

With `(venv)` showing in your prompt:
```bash
pip install -r requirements-dev.txt
```
This downloads and installs everything the backend needs (FastAPI,
the ML libraries, the test framework, etc.) - takes a minute or two.
You'll see a lot of text scroll by; that's normal. It worked if the
last line looks like `Successfully installed ...` with no red error
text above it.

**Common failure: no internet access, or a corporate/school network
blocking PyPI.** If `pip install` hangs or fails with a connection
error, you need internet access to `pypi.org` specifically - try a
different network (phone hotspot is a good test) before assuming
something's broken.

---

## Step 4: Set up your `.env` file (optional, but do it anyway)

Copy the example file:
```bash
cp .env.example .env
```
(Windows Command Prompt: `copy .env.example .env`)

Open `.env` in your editor. **You can leave every value as-is for
local development** - the app runs with zero configuration, using an
in-memory database and a rule-based/template fallback for anything
that would otherwise need MongoDB, Gemini, or Qdrant credentials. The
comments in `.env.example` explain what each variable is for and
where to get a real value later if you need one. `.env` itself is
already in `.gitignore` - **never commit it** once it has anything
real in it (see `docs/GIT_SETUP.md`).

---

## Step 5: Train the ML models (optional, but do it once)

```bash
python -m app.ml.train_classifier
python -m app.ml.train_priority
```
Each command trains one of the two algorithms against the real dataset
already included at `backend/data/comcast_complaints.csv`, and prints
its accuracy when done. This takes a few seconds. **You can skip this
entirely** - the app falls back to simpler rule-based logic
automatically if no trained model exists - but running it once gives
you the real, more-accurate ML models instead. See `docs/ALGORITHMS.md`
if you're curious how either one actually works.

---

## Step 6: Run the backend

Still inside `backend/`, with `(venv)` active:
```bash
uvicorn app.main:app --reload
```
You should see something like:
```
[loopline] Seeded demo admin account -> email: admin@loopline.io | password: ChangeMe123! ...
INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:8000
```
That admin email/password line is your login for the admin dashboard -
it's seeded automatically every time the server starts (see
`app/admin_seed.py`).

**Confirm it's really working**: open
[http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs) in your
browser. You should see an interactive API documentation page (Swagger
UI) listing every endpoint - you can even try them out directly from
that page. If the page doesn't load, the server isn't running or
something failed on startup - scroll up in the terminal for the actual
error.

`--reload` means the server automatically restarts whenever you save a
change to a backend file - leave this terminal window open and running
while you work.

**"Address already in use" error?** Something's already using port
8000 - either a previous `uvicorn` you forgot to stop (find and close
that terminal), or another program. Run on a different port instead:
`uvicorn app.main:app --reload --port 8001` (and update `API_BASE` in
`frontend/config.js` to match).

---

## Step 7: Run the frontend

The frontend is plain HTML/CSS/JavaScript - no build step, no `npm
install`. With the backend still running in its own terminal, just
open `frontend/index.html` directly in your browser (double-click it,
or drag it into an open browser window).

`frontend/config.js` already knows to point at `http://127.0.0.1:8000`
when you're running locally (opening the file directly counts as
local, whether that's `file://` or `localhost` - see the comment in
that file). You don't need to run a separate local web server for the
frontend, though `python -m http.server` from inside `frontend/` works
too if you prefer an actual `http://localhost` URL over `file://`.

**Try it out:**
1. Click "Sign Up", create a customer account (password needs 8+
   characters, one uppercase letter, and one of `! @ # $ % ^ & *`).
2. File a complaint. Watch it get auto-categorized.
3. Log out, go to `admin-login.html`, log in with the admin
   email/password printed in the backend terminal in Step 6.
4. Poke around the admin dashboard - filter, search, edit a complaint,
   check the analytics tab, try the AI chatbot (it'll give template
   answers unless you've set `GEMINI_API_KEY` - see
   `docs/RAG_CHATBOT.md`).

**Nothing happens when you click things / browser console shows
errors?** Open your browser's developer tools (F12, or right-click →
Inspect → Console tab) and see the actual error - it'll almost always
say either "failed to fetch" (backend isn't running, or you're on the
wrong port) or a specific validation message from the backend.

---

## Step 8: Run the tests

```bash
pytest
```
This runs the full automated test suite against the code as it
stands - it takes a few seconds and should end with something like
`103 passed` (the exact number grows over time as more gets added;
what matters is `passed`, not `failed` or `error`). This is the
fastest way to check "did my change break anything" before you commit.

There's also a slower, more real-world check:
```bash
# terminal 1 (leave running)
uvicorn app.main:app --reload

# terminal 2
python scripts/manual_api_smoke_check.py
```
This one starts a real server and hits it with real HTTP requests
(signup, login, file a complaint, admin actions, etc.) - closer to
what actually clicking through the browser does, useful after touching
anything auth- or routing-related. See `docs/TESTING.md` for the full
picture of what's been verified and how.

---

## Step 9: Find your way around the codebase

You don't need to read every file to get started - use this table to
jump straight to whatever you're actually trying to change:

| "I want to change/add..." | Look here |
|---|---|
| What happens when a complaint is filed | `backend/app/main.py` (`POST /complaints`) |
| The category-classification logic (Algorithm 1) | `backend/app/classify.py`, `backend/app/ml/train_classifier.py` |
| The priority-prediction logic (Algorithm 2) | `backend/app/priority.py`, `backend/app/ml/train_priority.py` |
| Signup/login rules (password strength, etc.) | `backend/app/auth.py` |
| What a request/response looks like (fields, types) | `backend/app/models.py` |
| The list of valid categories | `backend/app/categories.py` |
| The list of valid Myanmar cities (autofills state/zip) | `backend/app/cities.py` |
| Server-side complaint length / city checks | `backend/app/validation.py` |
| Anything admin-only | search `backend/app/main.py` for `/admin/` |
| The AI chatbot | `backend/app/chatbot.py`, `backend/app/rag/` |
| How the database connection works (or its fallback) | `backend/app/db.py` |
| A customer-facing page's look/behavior | `frontend/*.html` + matching `.js` file (e.g. `activities.html` ↔ `script.js`) |
| An admin page's look/behavior | `frontend/admin-*.html` + `admin*.js` |
| Shared styling | `frontend/style.css` |
| Where the frontend points its API calls | `frontend/config.js` |

For the bigger picture (why things are structured this way, not just
where they live), see `docs/ARCHITECTURE.md`. For the full list of
every endpoint and its exact request/response shape, see
`docs/API_REFERENCE.md`.

---

## Step 10: A worked example - make a real change, safely

This walks through the entire loop once: change code → see it take
effect → write a test for it → run the tests → (when you're ready)
commit it. We'll add a `version` field to the health-check endpoint -
small, harmless, and it touches both a backend file and a test file so
you see the whole pattern.

**1. Make the change.** Open `backend/app/main.py`, find:
```python
@app.get("/")
def health_check():
    return {"status": "ok"}
```
and change it to:
```python
@app.get("/")
def health_check():
    return {"status": "ok", "version": "1.0.0"}
```
Save the file. If `uvicorn --reload` is still running from Step 6, it
auto-restarts - check its terminal for `Application startup complete.`
again.

**2. Confirm it worked.** With the server running:
```bash
curl http://127.0.0.1:8000/
```
Expect: `{"status":"ok","version":"1.0.0"}`. (No `curl`? Just open
`http://127.0.0.1:8000/` in a browser tab instead - same result.)

**3. Write a test for it.** Open `backend/tests/test_api.py`, find:
```python
def test_health_check():
    resp = client.get("/")
    assert resp.status_code == 200
```
and add a line:
```python
def test_health_check():
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.json()["version"] == "1.0.0"
```

**4. Run the tests.**
```bash
pytest tests/test_api.py -k health_check -v
```
Expect: `1 passed`. Then run the whole suite once more to make sure
nothing else broke: `pytest` → expect `103 passed` (this doc doesn't
add a *new* test, it edits an existing one, so the total count doesn't
change).

**5. Undo it (since this was just practice), or commit it for real.**
To undo: change both files back to what they were above, save, and
confirm `pytest` still passes. To keep it: follow the commit/branch/PR
steps in `docs/GIT_SETUP.md`.

That's the whole loop you'll repeat for every real change: edit → run
the server or `curl`/browser to eyeball it → write or update a test →
`pytest` → commit.

---

## Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| `command not found: python` | Try `python3` instead (Mac/Linux almost always use `python3`), or Python isn't on your `PATH` - see Step 1. |
| `ModuleNotFoundError: No module named 'fastapi'` (or similar) | Your venv isn't activated - re-run the Step 3b command for your OS, confirm `(venv)` shows in your prompt, then re-run whatever command failed. |
| `pip install` fails with a connection/timeout error | No internet access to `pypi.org` - see Step 3c. |
| Signup rejects your password | Needs 8+ characters, at least one uppercase letter, and one of `! @ # $ % ^ & *` (e.g. `Passw0rd!` works, `password123` doesn't) - see `backend/app/auth.py`. |
| Signup rejects your name | Must start with a letter, 3-20 characters, letters/numbers/spaces only - no underscores, no punctuation. |
| Filing a complaint (via `curl`/Postman, not the UI) gets `400` | Complaint text must be 20-1000 characters, and `city` (if you send one at all) must be a real entry from `GET /cities` - see `app/validation.py`. The UI already enforces both before it ever sends the request, so this mostly shows up when testing the API directly. |
| `Address already in use` when starting `uvicorn` | Something's already on port 8000 - see Step 6. |
| Frontend shows "failed to fetch" / spinner never resolves | Backend isn't running, or is running on a different port than `frontend/config.js` expects - check the backend terminal, and check `API_BASE` in `config.js`. |
| `Invalid or expired session token` | You're logged out (or the backend restarted, which clears in-memory sessions) - log in again. |
| Admin pages show "Admin access required" (403) | You're logged in as a customer account, not the admin account - log in with the admin email/password printed on backend startup instead. |
| Chatbot gives a generic templated answer, not something specific | Expected with no `GEMINI_API_KEY` set - see `docs/RAG_CHATBOT.md` to enable the real thing. |
| `pytest` fails after you added a new file to `backend/scripts/` or similar | If its filename matches `test_*.py` or `*_test.py`, pytest tries to collect it as a test automatically - see `docs/DECISIONS.md` #20 for exactly this happening. Rename it to something else, e.g. `*_check.py`. |
| Git says you have "uncommitted changes" you don't remember making | Probably `venv/` or `__pycache__/` folders - both should already be in `.gitignore`; if `git status` still shows them, something's off with your `.gitignore` setup, ask a teammate. |

If you hit something not listed here, once you figure it out, add it
to this table for the next person - that's exactly how this table got
built in the first place.

---

## A short glossary

Terms that come up across the docs and might not be obvious yet:

- **Ticket / `ticket_no`**: the unique number assigned to each filed
  complaint (starts at 100001), used to look it up later.
- **Session token**: an opaque string returned on login, sent back as
  `Authorization: Bearer <token>` on every request that needs to know
  who you are - not your password, and not something meaningful on its
  own (see `docs/ARCHITECTURE.md`).
- **IDOR** (Insecure Direct Object Reference): a security bug class
  where an ID in a request (like `user_id`) is trusted from the client
  instead of verified server-side, letting someone access another
  user's data by just changing a number. Loopline avoids this by
  deriving `user_id` from the session token, never the request body -
  see `docs/DECISIONS.md` #9.
- **RAG** (Retrieval-Augmented Generation): instead of just asking an
  LLM a question, first search a knowledge base for relevant snippets
  and hand those to the LLM as context - so answers are grounded in
  actual documents instead of the model just guessing. That's what
  powers the Admin AI Chatbot - see `docs/RAG_CHATBOT.md`.
- **Weak/distant supervision**: training an ML model on labels that
  were themselves generated by a simpler rule-based system (rather
  than hand-labeled by a person) - how both Algorithm 1 and Algorithm
  2's training data was built here. See `docs/ALGORITHMS.md`.
- **TF-IDF**: a way of turning text into numbers a model can use, based
  on how often a word appears in a given document vs. how common it is
  across all documents - what Algorithm 1's category classifier uses
  to represent complaint text.
- **In-memory fallback**: when a real service (MongoDB, Qdrant) isn't
  configured, the app substitutes a simple in-Python-memory version of
  the same interface instead of failing - see `docs/ARCHITECTURE.md`'s
  "why this shape" section. Convenient for development; data doesn't
  survive a server restart.

---

## Where to go from here

Once the above all works and makes sense, the root `README.md` has a
full documentation map - `docs/ARCHITECTURE.md` for the bigger
picture, `docs/ALGORITHMS.md` for how the ML actually works,
`docs/API_REFERENCE.md` for every endpoint, and `docs/DECISIONS.md` for
the reasoning behind basically every non-obvious choice in this
codebase (genuinely worth skimming - a lot of "why is it done this
way, not that way" gets answered there before you need to ask).
