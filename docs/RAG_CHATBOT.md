# The RAG Chatbot

> **Current stack:** BM25 keyword retrieval (always available, no API)
> + optional Gemini query embeddings fused via Reciprocal Rank Fusion
> → Gemini `generateContent` for the final answer.
>
> See **docs/DECISIONS.md Decision 30** for why the original
> Gemini embeddings + Qdrant indexing was replaced by BM25.

---

## Quick answer for junior team: what goes in `data/knowledge_base/`?

**SOP (Standard Operating Procedure) documents — not the training
datasets.** This is the most common point of confusion:

| Thing | Used for | Format | Location |
|---|---|---|---|
| `comcast_complaints.csv` | Training **Algorithm 1** (category) and **Algorithm 2** (priority) | CSV | `backend/data/` |
| `synthetic_complaints.csv` | Dev-only fallback if the CSV is missing | CSV | `backend/data/` |
| SOP / playbook files | **RAG chatbot** knowledge base — what the admin AI searches | `.md`, `.txt`, or `.pdf` | `backend/data/knowledge_base/` |

The files in `data/knowledge_base/` (one per complaint category) are
Markdown SOP documents: step-by-step guides telling admins how to
handle billing disputes, technical outages, etc. When an admin asks
"how should I handle a repeat billing complaint?", the system searches
these documents for the most relevant chunks and hands them to Gemini
to generate a grounded answer.

**PDF files are fully supported.** Drop any `.pdf` into `data/
knowledge_base/` and re-run `python -m app.rag.knowledge_base` — it's
picked up automatically, no code changes needed.

**The training datasets are never read by the chatbot.** They only
train the ML models (which run locally, without Gemini). The two
pipelines are completely independent.

---

## Two chatbot consumers, one pipeline

- **Customer-facing widget** (`POST /chatbot/recommend`) — the
  floating chat widget on the homepage. Complaint text in,
  category + recommended action out.
- **Admin AI Chatbot** (`POST /admin/chatbot/ask`, SRS Module 3.2) —
  free-form Q&A for support agents, optionally scoped to a specific
  ticket, grounded in indexed SOP documents.

Both go through `app/chatbot.py`, which tries the real RAG pipeline
(`app/rag/pipeline.py`) first and falls back to a static template if
Gemini isn't configured or the call fails — same "never let an AI
integration break the request" rule used for the two ML algorithms.

---

## Architecture

```
Admin asks a question (optionally: "about ticket #100042")
        │
        ▼
1. BM25 search (app/rag/bm25_store.py)
   — pure Python, no API call, always available
   — strong for exact keyword matches ("billing", "outage", "escalation")
        │
        ▼
2. (Optional) Embed the query — Gemini embedContent, RETRIEVAL_QUERY
   then search the vector store (Qdrant if configured, in-memory fallback)
   — adds semantic coverage for paraphrases
   — silently skipped if GEMINI_API_KEY missing or embedding fails
        │
        ▼
3. Reciprocal Rank Fusion (app/rag/hybrid_retriever.py)
   — merges the BM25 and embedding ranked lists
   — score = Σ 1/(60 + rank_i) for each retriever that returned the chunk
   — chunks appearing in both lists score significantly higher
        │
        ▼
4. Build a grounded prompt: top-k fused SOP chunks + (optional ticket
   context) + the question, with a system instruction telling Gemini to
   answer from the context and say so plainly if it doesn't cover it
        │
        ▼
5. Gemini generateContent produces the answer
        │
        ▼
Returns {"answer": ..., "sources": [...], "used_rag": bool,
         "used_bm25": bool, "used_embeddings": bool}
```

---

## Indexing the knowledge base

`data/knowledge_base/` holds Markdown SOP documents. Build (or
rebuild) the BM25 index:

```bash
cd backend/
python -m app.rag.knowledge_base
```

Output when it works:
```
[knowledge_base] 5 document(s) → 2315 chunks
[knowledge_base] BM25 index saved → .bm25_index.json
[knowledge_base] Ready. No API calls needed — Gemini is only
                 used when an admin asks a question.
```

This runs completely offline — no Gemini API key needed at index time.
The index is saved as `data/knowledge_base/.bm25_index.json`. Re-run
it any time the SOP docs change.

To wipe the index and start fresh:
```bash
python -m app.rag.knowledge_base --clear
```

**What the indexing does NOT do (intentionally):**
- It does **not** embed the document chunks with Gemini. This would
  consume ≈2315 embedding calls (the full chunk count), burning through
  the free-tier 1000/day quota instantly. Instead, only the query is
  embedded at question time — one call per admin question, not thousands.
- It does **not** require Qdrant. The BM25 index is a local JSON file.

---

## Configuration

All in `.env` (see `.env.example`):

| Variable | Required? | Default | Notes |
|---|---|---|---|
| `GEMINI_API_KEY` | No — falls back to templates if unset | — | Get one at https://aistudio.google.com/apikey |
| `GEMINI_MODEL` | No | `gemini-flash-latest` | Google-maintained alias always pointing at the current GA Flash model. Pin a specific version if you need reproducibility. |
| `GEMINI_EMBEDDING_MODEL` | No | `gemini-embedding-001` | Only used for query embedding in hybrid mode. |
| `GEMINI_EMBEDDING_DIM` | No | `768` | Output embedding dimension. |
| `QDRANT_URL` | No — falls back to in-memory cosine search if unset | — | Only relevant for the hybrid embedding path. |
| `QDRANT_API_KEY` | Only if using Qdrant Cloud | — | |
| `QDRANT_COLLECTION` | No | `loopline_sop_chunks` | |

**Minimal working config (BM25-only, no embeddings):** just set
`GEMINI_API_KEY`. No Qdrant needed. The chatbot will use BM25 for
retrieval and Gemini only for generating the answer.

**Full hybrid config:** set `GEMINI_API_KEY` + `QDRANT_URL` (and
optionally `QDRANT_API_KEY`). You'll also need to have upserted
vectors into Qdrant separately — the current indexing script does not
do this automatically (by design, to avoid quota exhaustion).

---

## How the hybrid retriever works (app/rag/hybrid_retriever.py)

```python
class HybridRetriever:
    def search_bm25(self, query, top_k=5)     → list[dict]  # always runs
    def search_embeddings(self, query, top_k=5) → list[dict] # optional
    def fuse_results(self, bm25, emb, k=60)   → list[dict]  # RRF
    def search(self, query, top_k=5)           → list[dict]  # orchestrates all
```

**Reciprocal Rank Fusion (RRF):**
```
score(chunk) = Σ  1 / (k + rank_in_list_i)
```
where k=60 is the standard default (Cormack et al. 2009). A chunk
ranked #1 in BM25 and #1 in embeddings scores ≈ 2/61 ≈ 0.033. A chunk
ranked #5 in only one list scores 1/65 ≈ 0.015. Chunks that exact-match
the query dominate naturally because BM25 puts them at the top.

---

## Gemini API shapes (verified July 2026)

**Chat completion** — `POST https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent`
```json
{"contents": [{"parts": [{"text": "..."}]}]}
```
Header: `x-goog-api-key: <key>`. Response: `data.candidates[0].content.parts[*].text`.

**Single embedding** — `POST .../v1beta/models/{model}:embedContent`
```json
{
  "model": "models/gemini-embedding-001",
  "content": {"parts": [{"text": "..."}]},
  "taskType": "RETRIEVAL_QUERY",
  "outputDimensionality": 768
}
```
The `"model"` field inside the body is required even though it's also
in the URL — a real deployment hit a `400 Bad Request` traced to
omitting it (see docs/DECISIONS.md #24). Response: `data.embedding.values`.

**Batch embedding** — `:batchEmbedContents` with a `"requests"` array
(each item needs its own `"model"` field), response `data.embeddings[*].values`.
Current pipeline does NOT use batch embedding at index time — this is
intentional to avoid quota exhaustion.

**Qdrant** — `PUT /collections/{name}` to create, `PUT /collections/{name}/points`
to upsert, `POST /collections/{name}/points/search` to query. Header: `api-key: <key>`.

Sources:
- https://ai.google.dev/gemini-api/docs/embeddings
- https://ai.google.dev/gemini-api/docs/text-generation
- Qdrant REST API reference

---

## Failure modes handled

| Situation | Behaviour |
|---|---|
| No `GEMINI_API_KEY` | Template response, `used_rag: false`, no error |
| Gemini generation fails (timeout, bad key, rate limit) | Caught in `app/chatbot.py`; returns a plain-language error, not a 500 |
| Gemini embedding fails or times out | Silently falls back to BM25-only; no error surfaced |
| Qdrant unavailable | Silently falls back to BM25-only; no error surfaced |
| No knowledge base indexed yet (`--clear` was run, no rebuild) | Answer includes a note to run `python -m app.rag.knowledge_base` |
| BM25 finds no matches | Prompt tells Gemini the context doesn't cover it; Gemini answers from general knowledge |

**Error message in the admin chatbot UI:**
- Old (inaccurate): "The AI chatbot hit an error talking to Gemini/Qdrant..."
- New (accurate): "The AI chatbot hit an error generating a response... Keyword search (BM25) is still available — try rephrasing..."

---

## File map

| File | Role |
|---|---|
| `app/rag/bm25_store.py` | Pure-Python Okapi BM25 (k1=1.5, b=0.75), JSON persistence, thread-safe cache |
| `app/rag/hybrid_retriever.py` | `HybridRetriever`: BM25 + Gemini query embeddings + RRF fusion |
| `app/rag/gemini_client.py` | REST wrapper for Gemini `generateContent` and `embedContent` / `batchEmbedContents` |
| `app/rag/vector_store.py` | Qdrant REST wrapper + in-memory cosine fallback (used by embedding path) |
| `app/rag/knowledge_base.py` | Loads SOP docs, chunks them, builds BM25 index, saves `.bm25_index.json` |
| `app/rag/pipeline.py` | Calls `HybridRetriever.search()` → builds prompt → calls Gemini generate |
| `app/chatbot.py` | Entry points: `get_recommendation()` and `ask_admin_chatbot()` |

**Legacy / partially superseded:**
- `app/rag/vector_store.py` — still present and used by the embedding
  arm of `HybridRetriever`. The Qdrant path is only exercised if
  `QDRANT_URL` is set and vector data has been upserted.
- `gemini_client.embed_text` / `embed_texts` — `embed_text` is used by
  `HybridRetriever.search_embeddings()` for query-time embedding.
  `embed_texts` (batch) is no longer called anywhere in the live path;
  it remains as a utility for anyone who wants to manually seed Qdrant
  with a curated subset of chunks.

---

## Step-by-step setup (minimal: BM25 + Gemini generation only)

1. Get a free Gemini API key at https://aistudio.google.com/apikey
2. Add `GEMINI_API_KEY=your-key` to `backend/.env`
3. From `backend/`: `python -m app.rag.knowledge_base`
4. Start the server: `uvicorn app.main:app --reload`
5. Open the admin portal → AI Chatbot tab → ask a question

That's it. No Qdrant setup needed for the BM25-only path.

## Step-by-step setup (full hybrid: BM25 + embeddings + Qdrant)

1. Complete the minimal setup above.
2. Create a free Qdrant Cloud cluster at https://cloud.qdrant.io
3. Add `QDRANT_URL=https://your-cluster.qdrant.io` and
   `QDRANT_API_KEY=your-qdrant-key` to `backend/.env`
4. Manually seed Qdrant with a curated subset of high-value chunks
   (optional — the system works without this; the embedding path will
   just return empty results and fall back to BM25 silently).
