# Deployment (free-tier plan)

Everything here is chosen to be free or free-tier for a student
project - no code changes are needed to go from "runs locally with
in-memory fallbacks" to "runs for real," just environment variables.

## Pieces

| Piece | Where | Why |
|---|---|---|
| API | Render (free web service) | Deploys straight from GitHub, sleeps when idle on the free tier (fine for a demo/thesis project) |
| Database | MongoDB Atlas (M0 free tier, 512 MB) | Free forever, not just a trial |
| Vector store | Qdrant Cloud (free tier) or skip it | The in-memory fallback is genuinely fine for a knowledge base this size (a few dozen SOP chunks) - only bother with real Qdrant if you want it to survive server restarts without re-indexing |
| LLM | Gemini API | Pay-as-you-go with a free quota - get a key at https://aistudio.google.com/apikey |
| Frontend | Any static host (GitHub Pages, Netlify, Render static site) or just open the HTML files directly | Plain HTML/CSS/JS, no build step |

## Steps

### 1. MongoDB Atlas
1. Create a free M0 cluster at https://www.mongodb.com/cloud/atlas.
2. Database Access → add a user with a real password.
3. Network Access → allow access from anywhere (`0.0.0.0/0`) for
   simplicity, or Render's specific IPs if you want to lock it down.
4. Copy the connection string (`mongodb+srv://...`).

### 2. Deploy the API to Render
1. Push this repo to GitHub (see docs/GIT_SETUP.md if that's not done yet).
2. New → Web Service → connect the repo, root directory `backend/`.
3. Build command: `pip install -r requirements.txt`
   Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
4. Environment variables (Render's dashboard, not `.env` - `.env` is
   gitignored and won't be there): everything from `.env.example` -
   `MONGODB_URI`, `MONGODB_DB_NAME`, `ADMIN_EMAIL`, `ADMIN_USERNAME`,
   `ADMIN_PASSWORD`, `GEMINI_API_KEY`, `GEMINI_MODEL`,
   `GEMINI_EMBEDDING_MODEL`, `QDRANT_URL`, `QDRANT_API_KEY`,
   `QDRANT_COLLECTION`.
5. Deploy. The API auto-seeds the admin account on first startup (see
   docs/ADMIN_AUTH.md) - check Render's logs for the confirmation line.
6. Once it has real Mongo, also run `python -m data.seed_admin` locally
   with the same `MONGODB_URI` set, just to be certain the admin
   account exists in that exact database (the auto-seed only touches
   whichever DB *that specific running process* connects to).

### 3. Index the RAG knowledge base (optional, only if using Gemini)
Run once (locally, with `.env` pointing at the same `QDRANT_URL` the
deployed API uses, or from a one-off shell on Render):
```bash
python -m app.rag.knowledge_base
```

### 4. Point the frontend at the deployed API
Edit `frontend/config.js` - the `else` branch already has a
placeholder:
```js
: 'https://REPLACE-WITH-YOUR-DEPLOYED-API-URL.onrender.com';
```
Replace with the real Render URL. That's the only frontend change
needed - everything else already reads from `API_BASE`.

### 5. CORS
`app/main.py` currently allows all origins (`allow_origins=["*"]`) -
fine for development, worth tightening to the actual deployed frontend
URL before this goes anywhere someone else might poke at it.

## Loading the real complaint dataset

Once you have internet access somewhere:
1. Download the Kaggle dataset:
   https://www.kaggle.com/datasets/yasserh/comcast-telecom-complaints-dataset
2. Save it as `backend/data/comcast_complaints.csv` (exact filename
   matters - both training scripts and `load_dataset.py` look for it
   by that name first, see docs/ALGORITHMS.md).
3. Retrain both models against it:
   ```bash
   python -m app.ml.train_classifier
   python -m app.ml.train_priority
   ```
4. Load the historical rows into the database:
   ```bash
   python -m data.load_dataset data/comcast_complaints.csv
   ```
   (Point `MONGODB_URI` at wherever you want this loaded - local
   in-memory won't persist past the script exiting.)

## Costs to keep an eye on

- Render free tier: spins down after inactivity, cold-starts on the
  next request (a few seconds delay) - not a cost, just a UX thing to
  mention if demoing live.
- Gemini API: has a free quota; check current pricing/limits at
  https://ai.google.dev/pricing before assuming a specific number,
  since these change.
- MongoDB Atlas M0: free forever, but capped at 512 MB - more than
  enough for a complaint dataset at this scale.
