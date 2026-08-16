"""
Thin REST wrapper around the Gemini API - deliberately NOT using the
`google-genai` SDK package, for two reasons: (1) it isn't installed in
this dev sandbox and there's no internet access here to add it or
test it, and (2) a plain `requests`-based wrapper has zero extra
dependencies beyond what's already in requirements.txt, so it's one
less thing that can fail to install in an unfamiliar grading/CI
environment. Swap this for the official SDK later if useful - nothing
outside this file needs to change (same Strategy Pattern used
throughout - see app/classify.py).

Endpoints and request/response shapes below were verified against the
live Gemini API docs (ai.google.dev/gemini-api/docs) as of July 2026 -
see docs/RAG_CHATBOT.md for the citations. This code has NOT been run
against the real API from inside a dev/build sandbox (none used to
build or extend this project have had network access to
generativelanguage.googleapis.com specifically - confirmed directly,
not assumed, each time - see docs/TESTING.md and docs/DECISIONS.md
#20). A real deployment DID hit this code for real and got a 400 on
embedContent - see docs/DECISIONS.md #24 for the fix (embed_text() was
missing the "model" field in its body that embed_texts() already had,
and that every official example includes) and for why the error
message itself wasn't useful for diagnosing this the first time
(str(HTTPError) doesn't include the response body - now fixed via
_raise_with_body() below, so next time this happens the actual reason
from Google shows up directly in the admin chatbot UI).

Model choice: defaults to `gemini-flash-latest`, a Google-maintained
alias that always points at the current GA Flash model (gemini-3.5-flash
as of this writing) - avoids the project needing a manual bump every
time Google ships a new version. Override via GEMINI_MODEL in .env if
you want to pin a specific version instead.
"""
import os
import time

import requests

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-flash-latest")
GEMINI_EMBEDDING_MODEL = os.getenv("GEMINI_EMBEDDING_MODEL", "gemini-embedding-001")
GEMINI_EMBEDDING_DIM = int(os.getenv("GEMINI_EMBEDDING_DIM", "768"))

BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"
TIMEOUT_SECONDS = 20

# Gemini free tier: max 100 texts per batchEmbedContents call.
# We split into sub-batches and wait between them so a large knowledge
# base re-index doesn't exhaust the 1000/day quota in one burst.
# Override via .env if you upgrade to a paid tier with higher limits.
EMBED_BATCH_SIZE = int(os.getenv("GEMINI_EMBED_BATCH_SIZE", "50"))
EMBED_BATCH_DELAY = float(os.getenv("GEMINI_EMBED_BATCH_DELAY", "2.0"))  # seconds


class GeminiError(Exception):
    """Raised for any Gemini API problem - callers (app/rag/pipeline.py)
    catch this and fall back to the template response rather than
    letting a chatbot call ever break the request."""


def is_configured() -> bool:
    return bool(GEMINI_API_KEY)


def _headers():
    return {"Content-Type": "application/json", "x-goog-api-key": GEMINI_API_KEY}


def _raise_with_body(e: requests.RequestException, action: str):
    """Wraps a requests error, including the actual response body if
    there is one - Google's error responses put the real reason
    (INVALID_ARGUMENT vs. FAILED_PRECONDITION vs. PERMISSION_DENIED,
    etc.) in the JSON body, which `str(HTTPError)` alone does NOT
    include (it only gives the status line, e.g. "400 Client Error:
    Bad Request for url: ..."). Without this, a 400 with a billing/
    region problem and a 400 with a malformed request look identical
    in the admin chatbot UI and in logs - see docs/DECISIONS.md #24."""
    body = ""
    if getattr(e, "response", None) is not None:
        try:
            body = f" | response body: {e.response.text}"
        except Exception:
            pass
    raise GeminiError(f"Gemini {action} request failed: {e}{body}") from e


def generate_text(prompt: str, system_instruction: str = None) -> str:
    """Calls :generateContent and returns the plain text response."""
    if not is_configured():
        raise GeminiError("GEMINI_API_KEY is not set.")

    body = {"contents": [{"parts": [{"text": prompt}]}]}
    if system_instruction:
        body["systemInstruction"] = {"parts": [{"text": system_instruction}]}

    url = f"{BASE_URL}/{GEMINI_MODEL}:generateContent"
    try:
        resp = requests.post(url, headers=_headers(), json=body, timeout=TIMEOUT_SECONDS)
        resp.raise_for_status()
        data = resp.json()
        candidates = data.get("candidates") or []
        if not candidates:
            raise GeminiError(f"No candidates in Gemini response: {data}")
        parts = candidates[0].get("content", {}).get("parts", [])
        text = "".join(p.get("text", "") for p in parts)
        if not text:
            raise GeminiError(f"Empty text in Gemini response: {data}")
        return text
    except requests.RequestException as e:
        _raise_with_body(e, "generateContent")


def embed_text(text: str, task_type: str = "RETRIEVAL_DOCUMENT") -> list:
    """Returns a single embedding vector (list of floats) for one
    string. task_type should be RETRIEVAL_DOCUMENT when indexing
    knowledge-base chunks, RETRIEVAL_QUERY when embedding an incoming
    question/complaint to search against them - this asymmetric setup
    is Google's documented recommendation for retrieval use cases."""
    if not is_configured():
        raise GeminiError("GEMINI_API_KEY is not set.")

    url = f"{BASE_URL}/{GEMINI_EMBEDDING_MODEL}:embedContent"
    body = {
        # Every official example (curl, Postman, the OpenClaw issue
        # confirming a working response) includes "model" inside the
        # body too, even though it's already in the URL path - this
        # function used to omit it while embed_texts() (below) always
        # included it per-item. That inconsistency is the most likely
        # cause of the real 400 this was hit with - see
        # docs/DECISIONS.md #24 for the sources checked.
        "model": f"models/{GEMINI_EMBEDDING_MODEL}",
        "content": {"parts": [{"text": text}]},
        "taskType": task_type,
        "outputDimensionality": GEMINI_EMBEDDING_DIM,
    }
    try:
        resp = requests.post(url, headers=_headers(), json=body, timeout=TIMEOUT_SECONDS)
        resp.raise_for_status()
        data = resp.json()
        values = data.get("embedding", {}).get("values")
        if not values:
            raise GeminiError(f"No embedding values in Gemini response: {data}")
        return values
    except requests.RequestException as e:
        _raise_with_body(e, "embedContent")


def _retry_delay_from_429(resp: requests.Response) -> float:
    """Read the retryDelay from Google's 429 body (e.g. '4.59s').
    Falls back to 10 seconds if unparseable."""
    try:
        for detail in resp.json().get("error", {}).get("details", []):
            if "retryDelay" in detail:
                s = detail["retryDelay"].rstrip("s")
                return float(s) + 1.0  # add 1 s safety margin
    except Exception:
        pass
    return 10.0


def _embed_one_batch(texts: list, task_type: str, max_retries: int = 4) -> list:
    """Sends one batchEmbedContents call (≤ EMBED_BATCH_SIZE items).
    Retries automatically on 429 using the delay Google includes in
    the response body."""
    url = f"{BASE_URL}/{GEMINI_EMBEDDING_MODEL}:batchEmbedContents"
    body = {
        "requests": [
            {
                "model": f"models/{GEMINI_EMBEDDING_MODEL}",
                "content": {"parts": [{"text": t}]},
                "taskType": task_type,
                "outputDimensionality": GEMINI_EMBEDDING_DIM,
            }
            for t in texts
        ]
    }
    for attempt in range(max_retries):
        try:
            resp = requests.post(url, headers=_headers(), json=body,
                                 timeout=TIMEOUT_SECONDS * 2)
            if resp.status_code == 429:
                wait = _retry_delay_from_429(resp)
                print(f"[gemini] Rate limited — waiting {wait:.1f}s "
                      f"(attempt {attempt + 1}/{max_retries})…")
                time.sleep(wait)
                continue
            resp.raise_for_status()
            data = resp.json()
            embeddings = data.get("embeddings") or []
            if len(embeddings) != len(texts):
                raise GeminiError(
                    f"batchEmbedContents returned {len(embeddings)} vectors "
                    f"for {len(texts)} inputs: {data}"
                )
            return [e["values"] for e in embeddings]
        except requests.RequestException as e:
            if attempt == max_retries - 1:
                _raise_with_body(e, "batchEmbedContents")
            time.sleep(2 ** attempt)
    raise GeminiError("batchEmbedContents failed after all retries")


def embed_texts(texts: list, task_type: str = "RETRIEVAL_DOCUMENT") -> list:
    """Embeds a list of texts, splitting into sub-batches of
    EMBED_BATCH_SIZE (default 50) so we stay inside Gemini's 100-per-
    request limit and don't blow the daily free-tier quota in one burst.
    Waits EMBED_BATCH_DELAY seconds between sub-batches.

    Previous version sent ALL chunks in one request - this caused a
    400 when chunks > 100 (Gemini's batchEmbedContents limit), which
    then fell back to N individual embed_text() calls, burning through
    the 1000/day free-tier quota in seconds. See docs/DECISIONS.md #30.
    """
    if not is_configured():
        raise GeminiError("GEMINI_API_KEY is not set.")
    if not texts:
        return []

    total = len(texts)
    all_vectors = []
    for start in range(0, total, EMBED_BATCH_SIZE):
        sub = texts[start:start + EMBED_BATCH_SIZE]
        batch_num = start // EMBED_BATCH_SIZE + 1
        total_batches = (total + EMBED_BATCH_SIZE - 1) // EMBED_BATCH_SIZE
        print(f"[gemini] Embedding batch {batch_num}/{total_batches} "
              f"({len(sub)} chunks)…")
        all_vectors.extend(_embed_one_batch(sub, task_type))
        # Sleep between sub-batches (not after the last one)
        if start + EMBED_BATCH_SIZE < total:
            time.sleep(EMBED_BATCH_DELAY)

    return all_vectors
