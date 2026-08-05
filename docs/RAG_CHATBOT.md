# The RAG chatbot (Gemini + Qdrant)

## Quick answer for junior team: what goes in `data/knowledge_base/`?

**SOP (Standard Operating Procedure) documents — not the training
datasets.** This is the most common point of confusion:

| Thing | Used for | Format | Location |
|---|---|---|---|
| `comcast_complaints.csv` | Training **Algorithm 1** (category) and **Algorithm 2** (priority) | CSV | `backend/data/` |
| `synthetic_complaints.csv` | Dev-only fallback if the CSV is missing | CSV | `backend/data/` |
| SOP / playbook files | **RAG chatbot** knowledge base — what the admin AI searches | `.md`, `.txt`, or `.pdf` | `backend/data/knowledge_base/` |

The five files already in `data/knowledge_base/` (one per complaint
category) are Markdown SOP documents: step-by-step guides that tell an
admin how to handle billing disputes, technical outages, etc. When an
admin asks the chatbot "how should I handle a repeat billing complaint?",
the chatbot embeds the question, searches Qdrant for the most relevant
SOP chunks, and hands those to Gemini to generate a grounded answer.

**PDF files are fully supported.** Drop any `.pdf` into `data/
knowledge_base/` and re-run `python -m app.rag.knowledge_base` — it
gets picked up automatically, no code changes needed. A real internal
SOP manual PDF is a great fit here.

**The training datasets are never read by the chatbot.** They only
train the ML models (which run locally, without Gemini). The two
pipelines are completely independent.

---

Two chatbot consumers, one underlying pipeline:

- **Customer-facing widget** (`POST /chatbot/recommend`) - the
  floating chat widget on the homepage. Simple: complaint text in,
  category + a recommended action out.
- **Admin AI Chatbot** (`POST /admin/chatbot/ask`, SRS Module 3.2) -
  free-form Q&A for support agents, optionally scoped to a specific
  ticket, grounded in indexed SOP documents.

Both go through `app/chatbot.py`, which tries the real RAG pipeline
(`app/rag/pipeline.py`) first and falls back to a static template if
Gemini isn't configured or the call fails for any reason - same
"never let an AI integration break the request" rule used for the two
ML algorithms.

## Why Gemini + Qdrant

Chosen because that's what was specified for this build (see
DECISIONS.md). Both are used over **plain REST calls via `requests`**
rather than their official SDK packages (`google-genai`,
`qdrant-client`) - the environment this was built in has neither
package installed and no internet access to add or test them, and a
`requests`-based wrapper is one fewer dependency that has to install
correctly on someone else's machine. Swap either for the official SDK
later without touching anything outside `app/rag/gemini_client.py` /
`app/rag/vector_store.py`.

**⚠️ Not runtime-tested against the real APIs** - see docs/TESTING.md.
The request/response shapes below were verified against the live API
documentation (not from training-data memory, which would be stale -
see the citations), but no actual HTTP call has been made against
Gemini or Qdrant from this codebase yet. Test this first once you have
real API keys.

## Architecture

```
Admin asks a question (optionally: "about ticket #100042")
        │
        ▼
1. Embed the question — Gemini embedContent, task_type=RETRIEVAL_QUERY
        │
        ▼
2. Search the vector store for the top-k closest SOP chunks
   (Qdrant if QDRANT_URL is set, else an in-memory brute-force
    cosine-similarity fallback - app/rag/vector_store.py)
        │
        ▼
3. Build a grounded prompt: SOP context + (optional ticket context)
   + the question, with a system instruction telling Gemini to answer
   from the context and say so plainly if the context doesn't cover it
        │
        ▼
4. Gemini generateContent produces the answer
        │
        ▼
Returns {"answer": ..., "sources": [...], "used_rag": true}
```

## Indexing the knowledge base

`data/knowledge_base/` holds 5 markdown SOP documents (Billing,
Financial, Technical, Service, Others) written for this project -
resolution steps, escalation criteria, response-time targets per
category. Real SOP PDFs can be dropped into the same folder; `app/rag/
knowledge_base.py` picks up `.pdf` files too via `pypdf` text
extraction, no code changes needed.

Build (or rebuild) the index:
```bash
python -m app.rag.knowledge_base
```
This chunks each document (paragraph-aware, ~800 characters per
chunk), embeds every chunk via Gemini's `batchEmbedContents`
(`task_type=RETRIEVAL_DOCUMENT` - the asymmetric embedding setup
Google's docs recommend for retrieval use cases), and upserts into the
vector store. Re-run it any time the SOP docs change.

## Configuration

All in `.env` (see `.env.example`):

| Variable | Required? | Default | Notes |
|---|---|---|---|
| `GEMINI_API_KEY` | No - falls back to templates if unset | — | Get one at https://aistudio.google.com/apikey |
| `GEMINI_MODEL` | No | `gemini-flash-latest` | A Google-maintained alias that always points at the current GA Flash model (`gemini-3.5-flash` as of July 2026) - avoids needing a manual version bump later. Pin a specific version instead if you want fully reproducible behavior. |
| `GEMINI_EMBEDDING_MODEL` | No | `gemini-embedding-001` | Stable embedding model; `gemini-embedding-2-preview` supports Matryoshka dimensionality reduction and multimodal input if you need that later. |
| `GEMINI_EMBEDDING_DIM` | No | `768` | Output embedding size. |
| `QDRANT_URL` | No - falls back to in-memory search if unset | — | e.g. a free Qdrant Cloud cluster, or `http://localhost:6333` for a local Docker instance |
| `QDRANT_API_KEY` | Only if using Qdrant Cloud | — | |
| `QDRANT_COLLECTION` | No | `loopline_sop_chunks` | |

## API shapes this was built against (verified July 2026, corrected
## against a real 400 error - see docs/DECISIONS.md #24)

**Chat completion** - `POST https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent`
```json
{"contents": [{"parts": [{"text": "..."}]}]}
```
Header: `x-goog-api-key: <key>`. Response:
`data.candidates[0].content.parts[*].text`.

**Embeddings** - `POST .../v1beta/models/{model}:embedContent`
```json
{"model": "models/gemini-embedding-001", "content": {"parts": [{"text": "..."}]}, "taskType": "RETRIEVAL_DOCUMENT", "outputDimensionality": 768}
```
The `"model"` field inside the body is easy to assume is redundant
(the model is already in the URL) and skip - don't. A real deployment
hit a `400 Bad Request` traced to exactly that omission in
`embed_text()` (see docs/DECISIONS.md #24) - every official example
includes it. Response: `data.embedding.values`. Batch version:
`:batchEmbedContents` with a `"requests"` array (each item needs its
own `"model"` field too), response `data.embeddings[*].values`.

If you hit a `400` here: the error shown in the admin chatbot UI now
includes Google's actual response body (see `app/rag/gemini_client.py`'s
`_raise_with_body()`), not just the HTTP status line - read that first.
A bare 400 with no useful body text is more likely a project-level
issue (billing not enabled, free tier unavailable in your region) than
a malformed request - check the Google AI Studio / Cloud console
directly rather than only re-reading this code.

**Qdrant** - `PUT /collections/{name}` to create (`{"vectors": {"size":
N, "distance": "Cosine"}}`), `PUT /collections/{name}/points` to
upsert (`{"points": [{"id", "vector", "payload"}]}`), `POST
/collections/{name}/points/search` to query (`{"vector", "limit",
"with_payload": true}`). Header: `api-key: <key>`.

Source: https://ai.google.dev/gemini-api/docs/embeddings and
https://ai.google.dev/gemini-api/docs/text-generation (Gemini), and
Qdrant's REST API reference (Qdrant), both fetched directly while
building this rather than relied on from training-data memory, since
API details are exactly the kind of thing that goes stale.

## Failure modes handled

- No `GEMINI_API_KEY` → template response, `used_rag: false`, no error.
- `GEMINI_API_KEY` set but the call fails (bad key, network, rate
  limit, quota) → caught in `app/chatbot.py`, returns a plain-language
  error message instead of a 500.
- No knowledge base indexed yet → `vector_store.search()` returns an
  empty list, the prompt says so explicitly rather than hallucinating
  context, Gemini is told to say the context doesn't cover it.
