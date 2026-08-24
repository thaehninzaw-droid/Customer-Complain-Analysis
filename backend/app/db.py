"""
MongoDB connection helper.

If MONGODB_URI is not set in the environment, this falls back to a
simple in-memory store so you can run and test the whole API locally
before MongoDB Atlas is set up. Once MONGODB_URI is set (see
.env.example), it automatically switches to real MongoDB - no other
code needs to change.

get_collection(name) works for any collection - "users" and
"complaints" each get their own store.

In-memory store design notes:
- All find/find_one calls return COPIES of stored dicts, never
  references. This prevents callers from accidentally mutating stored
  state, which caused intermittent data corruption.
- insert_one deduplicates user documents by email on hot-reload so
  uvicorn --reload doesn't seed the admin user twice.
- find() deduplicates by semantic key (email for users, ticket_no for
  complaints) as a safety net for any duplication that slips through.
- Thread safety: a threading.Lock guards all writes. FastAPI runs
  handlers concurrently; without the lock, two simultaneous signups
  can both pass the "email exists?" check and insert duplicate users.
"""
import os
import threading
from copy import deepcopy
from itertools import count

from dotenv import load_dotenv

load_dotenv()

MONGODB_URI = os.getenv("MONGODB_URI")
DB_NAME = os.getenv("MONGODB_DB_NAME", "complaints_db")


class _InMemoryCollection:
    """Thread-safe, copy-safe in-memory pymongo stand-in.

    Supported query operators: equality, $in, $nin.
    Supported projection: {field: 1} include-only.
    All reads return shallow copies — callers can mutate freely.
    """

    def __init__(self):
        self._docs: list[dict] = []
        self._ids = count(1)
        self._lock = threading.Lock()

    # ── helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _matches(doc: dict, query: dict) -> bool:
        for key, condition in query.items():
            val = doc.get(key)
            if isinstance(condition, dict):
                if "$in"  in condition and val not in condition["$in"]:
                    return False
                if "$nin" in condition and val in condition["$nin"]:
                    return False
            else:
                if val != condition:
                    return False
        return True

    @staticmethod
    def _project(doc: dict, projection: dict | None) -> dict:
        """Return a shallow copy with optional field inclusion filter.
        Always returns a copy — never the live dict."""
        if not projection:
            return dict(doc)          # ← copy, never the live reference
        include = {k for k, v in projection.items() if v}
        include.add("_id")
        return {k: v for k, v in doc.items() if k in include}

    def _unique_docs(self) -> list[dict]:
        """Return deduplicated snapshot of _docs (no lock needed —
        caller holds it or is in a read-only context)."""
        seen: set = set()
        result = []
        for d in self._docs:
            if "role" in d and "email" in d:
                key = ("user", d["email"])
            elif "ticket_no" in d:
                key = ("ticket", d["ticket_no"])
            else:
                key = ("other", d.get("_id"))
            if key not in seen:
                seen.add(key)
                result.append(d)
        return result

    # ── write ──────────────────────────────────────────────────────────

    def insert_one(self, doc: dict) -> dict:
        doc = dict(doc)
        with self._lock:
            doc["_id"] = next(self._ids)
            # Deduplicate user documents by email to survive hot-reload.
            # Complaint documents (no 'role' field) are never blocked.
            if "role" in doc:
                email = doc.get("email", "")
                if any(d.get("email") == email and "role" in d
                       for d in self._docs):
                    return dict(doc)   # already exists — return copy, skip append
            self._docs.append(doc)
        return dict(doc)   # return copy so caller can't mutate stored state

    def update_one(self, query: dict, update: dict) -> dict | None:
        """Only supports {"$set": {...}}."""
        with self._lock:
            for d in self._docs:
                if self._matches(d, query):
                    if "$set" in update:
                        d.update(update["$set"])
                    return dict(d)   # return copy of updated doc
        return None

    # ── read ───────────────────────────────────────────────────────────

    def find(self, query: dict = None,
             projection: dict = None) -> list[dict]:
        with self._lock:
            docs = self._unique_docs()
        if not query:
            return [self._project(d, projection) for d in docs]
        return [
            self._project(d, projection)
            for d in docs
            if self._matches(d, query)
        ]

    def find_one(self, query: dict = None) -> dict | None:
        with self._lock:
            if not query:
                return dict(self._docs[0]) if self._docs else None
            for d in self._docs:
                if self._matches(d, query):
                    return dict(d)   # copy — never the live reference
        return None


# Module-level store — one collection per name, survives the process lifetime.
# On uvicorn --reload this dict is reinitialised (new process), which is
# expected: in-memory data is intentionally ephemeral.
_fallback_collections: dict[str, _InMemoryCollection] = {}
_collections_lock = threading.Lock()


def get_collection(name: str = "complaints") -> "_InMemoryCollection":
    """Return the named collection.

    Real MongoDB when MONGODB_URI is set (connection pooled via a
    module-level client so we don't open a new socket on every request).
    In-memory fallback otherwise.
    """
    if MONGODB_URI:
        return _get_mongo_collection(name)
    with _collections_lock:
        if name not in _fallback_collections:
            _fallback_collections[name] = _InMemoryCollection()
        return _fallback_collections[name]


# ── MongoDB connection pool ────────────────────────────────────────────────
# One MongoClient per process — pymongo handles connection pooling internally.
# Previous code called MongoClient(MONGODB_URI) inside get_collection(),
# opening a new TCP connection on EVERY request. That's a connection leak.
_mongo_client = None
_mongo_client_lock = threading.Lock()


def _get_mongo_collection(name: str):
    global _mongo_client
    if _mongo_client is None:
        with _mongo_client_lock:
            if _mongo_client is None:          # double-checked locking
                from pymongo import MongoClient
                _mongo_client = MongoClient(MONGODB_URI)
    return _mongo_client[DB_NAME][name]
