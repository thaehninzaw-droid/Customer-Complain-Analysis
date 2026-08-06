"""
Vector storage for the RAG knowledge base - Qdrant if QDRANT_URL is
configured, otherwise an in-memory brute-force cosine-similarity
fallback. SAME PATTERN as app/db.py's Mongo/in-memory switch: write
code once against get_store(), and it works with zero setup locally
and against real Qdrant once configured - no other file needs to
change either way.

Uses Qdrant's plain REST API via `requests` rather than the
`qdrant-client` SDK package, for the same reason as gemini_client.py:
one fewer dependency that has to be installed correctly, and this
sandbox has no internet access to verify the SDK against anyway.
Endpoint shapes verified against Qdrant's REST API docs as of July
2026 - see docs/RAG_CHATBOT.md.
"""
import math
import os

import requests

QDRANT_URL = os.getenv("QDRANT_URL")  # e.g. https://xyz.qdrant.io or http://localhost:6333
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
COLLECTION_NAME = os.getenv("QDRANT_COLLECTION", "loopline_sop_chunks")
TIMEOUT_SECONDS = 15


class VectorStoreError(Exception):
    pass


def is_configured() -> bool:
    return bool(QDRANT_URL)


# --------------------------------------------------------------- Qdrant ----

def _headers():
    headers = {"Content-Type": "application/json"}
    if QDRANT_API_KEY:
        headers["api-key"] = QDRANT_API_KEY
    return headers


def _qdrant_ensure_collection(vector_size: int):
    url = f"{QDRANT_URL}/collections/{COLLECTION_NAME}"
    resp = requests.get(url, headers=_headers(), timeout=TIMEOUT_SECONDS)
    if resp.status_code == 200:
        return
    resp = requests.put(
        url, headers=_headers(), timeout=TIMEOUT_SECONDS,
        json={"vectors": {"size": vector_size, "distance": "Cosine"}},
    )
    if resp.status_code not in (200, 201):
        raise VectorStoreError(f"Failed to create Qdrant collection: {resp.status_code} {resp.text}")


def _qdrant_upsert(points: list):
    url = f"{QDRANT_URL}/collections/{COLLECTION_NAME}/points"
    resp = requests.put(url, headers=_headers(), timeout=TIMEOUT_SECONDS, json={"points": points})
    if resp.status_code not in (200, 201):
        raise VectorStoreError(f"Failed to upsert points into Qdrant: {resp.status_code} {resp.text}")


def _qdrant_search(vector: list, top_k: int):
    url = f"{QDRANT_URL}/collections/{COLLECTION_NAME}/points/search"
    resp = requests.post(
        url, headers=_headers(), timeout=TIMEOUT_SECONDS,
        json={"vector": vector, "limit": top_k, "with_payload": True},
    )
    if resp.status_code == 404:
        # Collection doesn't exist = knowledge base was never indexed.
        # Give an actionable message so the admin (and any error log)
        # knows exactly what to run, rather than a raw Qdrant JSON blob.
        raise VectorStoreError(
            f"Knowledge base not indexed yet — run "
            f"`python -m app.rag.knowledge_base` from the backend/ "
            f"folder (needs GEMINI_API_KEY in .env). "
            f"See docs/GETTING_STARTED.md Step 11 or docs/RAG_CHATBOT.md."
        )
    if resp.status_code != 200:
        raise VectorStoreError(f"Qdrant search failed: {resp.status_code} {resp.text}")
    return [
        {"score": r["score"], "payload": r.get("payload", {})}
        for r in resp.json().get("result", [])
    ]


# ----------------------------------------------------------- in-memory ----
# Only used when QDRANT_URL isn't set - a real vector index this is not
# (no ANN, pure O(n) cosine similarity), but for a knowledge base of a
# few dozen SOP chunks that's completely fine, and it means the whole
# RAG pipeline is testable with zero external services.

_memory_points = []  # list of {"id", "vector", "payload"}


def _cosine(a: list, b: list) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _memory_upsert(points: list):
    by_id = {p["id"]: p for p in _memory_points}
    for p in points:
        by_id[p["id"]] = p
    _memory_points.clear()
    _memory_points.extend(by_id.values())


def _memory_search(vector: list, top_k: int):
    scored = [
        {"score": _cosine(vector, p["vector"]), "payload": p.get("payload", {})}
        for p in _memory_points
    ]
    scored.sort(key=lambda r: r["score"], reverse=True)
    return scored[:top_k]


# ------------------------------------------------------------- public ----

def ensure_collection(vector_size: int):
    if is_configured():
        _qdrant_ensure_collection(vector_size)
    # in-memory: nothing to provision


def upsert(points: list):
    """points: list of {"id": int, "vector": [float,...], "payload": {...}}"""
    if is_configured():
        _qdrant_upsert(points)
    else:
        _memory_upsert(points)


def search(vector: list, top_k: int = 4):
    """Returns [{"score": float, "payload": {...}}, ...] sorted best
    first."""
    if is_configured():
        return _qdrant_search(vector, top_k)
    return _memory_search(vector, top_k)


def reset_memory_store():
    """Testing/dev helper - clears the in-memory fallback so a
    re-index run doesn't just keep appending duplicates across
    process restarts within the same test session."""
    _memory_points.clear()
