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
| Admin AI Chatbot (RAG: Gemini + Qdrant) | ✅ Built, ⚠️ not yet tested against real API keys |
| Full FastAPI HTTP layer test pass | ✅ Confirmed - CI is green (see `docs/TESTING.md`) |
| Real Kaggle dataset loaded | ✅ Done - `backend/data/comcast_complaints.csv`, both models retrained against it (see `docs/ALGORITHMS.md`) |
| Pushed to a real GitHub remote | ✅ Done - CI running on every push |
| Deployed (Render/Atlas/Qdrant Cloud) | ❌ Not yet - see `docs/DEPLOYMENT.md` for the plan |
| CI (GitHub Actions running tests on push) | ✅ Done and green - `.github/workflows/tests.yml` |
| Real Gemini/Qdrant calls tested | ❌ Not yet - CI has no API keys configured (correctly) |
| Real MongoDB Atlas tested | ❌ Not yet - CI and local dev both use the in-memory fallback |

## Immediate next steps (in order)

1. **Get a real Gemini API key** (free quota at
   https://aistudio.google.com/apikey), set `GEMINI_API_KEY` locally,
   run `python -m app.rag.knowledge_base`, and ask the admin chatbot a
   real question. This is now the single biggest untested surface -
   CI deliberately has no API keys configured, so the Gemini/Qdrant
   REST calls have never actually executed anywhere (see
   `docs/TESTING.md`). Confirm `used_rag: true` comes back, not the
   fallback message.
2. **Click through both flows manually, at least once, with your own
   eyes.** Customer: signup → file a complaint → see it in Activities
   with an auto-assigned category. Admin: admin login → dashboard
   loads with real 2015 complaint history in the charts (including
   the June 2015 spike - see `docs/ALGORITHMS.md`) → filter/search/
   paginate the table → add a complaint manually → inline-edit a
   status → AI Chatbot page answers a question. CI proves the API
   responds correctly; it doesn't prove the pages look/feel right.
3. **Decide whether to test the real MongoDB Atlas path.** Both CI and
   local dev currently run against the in-memory fallback only - the
   real-pymongo branch has never executed anywhere. Either set up an
   Atlas cluster and test against it locally (`docs/DEPLOYMENT.md` has
   the steps), or add `MONGODB_URI` as a GitHub Actions secret so CI
   covers it too (`docs/TESTING.md` has the how).
4. **Deploy for real** if you want the demo to not depend on a laptop
   being open - `docs/DEPLOYMENT.md` has the full Render + Atlas +
   Qdrant Cloud walkthrough, all free-tier.

## Medium-term (nice to have before the defense)

- ~~If there's internet access anywhere in the pipeline, confirm the
  real XGBoost path works~~ **Confirmed via CI** - see
  `docs/TESTING.md`.
- Resolve the Billing/Financial category overlap (still an open
  question - see `docs/DECISIONS.md`'s "Open questions" section).
- Get the actual thesis rubric and check this against it directly,
  rather than against a best-guess of "needs an algorithm, data
  analysis, and a recommendation."

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

## Document map

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
