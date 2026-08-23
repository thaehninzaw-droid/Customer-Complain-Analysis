"""
MongoDB connection helper.

If MONGODB_URI is not set in the environment, this falls back to a
simple in-memory store so you can run and test the whole API locally
before MongoDB Atlas is set up. Once MONGODB_URI is set (see
.env.example), it automatically switches to real MongoDB - no other
code needs to change.

get_collection(name) works for any collection - "users" and
"complaints" each get their own store.
"""
import os
from itertools import count

from dotenv import load_dotenv

load_dotenv()

MONGODB_URI = os.getenv("MONGODB_URI")
DB_NAME = os.getenv("MONGODB_DB_NAME", "complaints_db")


class _InMemoryCollection:
    """Minimal stand-in for a pymongo collection. Only used when
    MONGODB_URI isn't set yet. Not for production use - data is lost
    when the process restarts.

    Supported query operators: equality, $in, $nin.
    Supported projection: {field: 1} include-only (excludes all others).
    """

    def __init__(self):
        self._docs = []
        self._ids = count(1)

    # ── write ──────────────────────────────────────────────────────────
    def insert_one(self, doc):
        doc = dict(doc)
        doc["_id"] = next(self._ids)
        # Dedup guard for hot-reload: only applies to user documents
        # (which always have a 'role' field). Complaint documents also
        # carry user_id but must never be blocked by this check.
        if "role" in doc:
            # Admin: deduplicate by email
            if doc.get("role") == "admin":
                if any(d.get("email") == doc["email"] for d in self._docs):
                    return doc
            # Customer: deduplicate by email (not user_id — that's assigned
            # by the API layer which already checks for uniqueness)
            else:
                if any(
                    d.get("role") == doc["role"] and d.get("email") == doc.get("email")
                    for d in self._docs
                ):
                    return doc
        self._docs.append(doc)
        return doc

    def update_one(self, query, update):
        """Only supports the {"$set": {...}} shape - that's all this
        app ever sends."""
        match = self.find_one(query)
        if match is None:
            return None
        if "$set" in update:
            match.update(update["$set"])
        return match

    # ── read ───────────────────────────────────────────────────────────
    @staticmethod
    def _matches(doc: dict, query: dict) -> bool:
        """Return True if doc satisfies every clause in query.
        Supports: equality, {$in: [...]}, {$nin: [...]}."""
        for key, condition in query.items():
            val = doc.get(key)
            if isinstance(condition, dict):
                if "$in" in condition and val not in condition["$in"]:
                    return False
                if "$nin" in condition and val in condition["$nin"]:
                    return False
            else:
                if val != condition:
                    return False
        return True

    @staticmethod
    def _project(doc: dict, projection: dict | None) -> dict:
        """Apply an include-only projection {field: 1, ...}.
        _id is always included unless explicitly set to 0."""
        if not projection:
            return doc
        include = {k for k, v in projection.items() if v}
        include.add("_id")
        return {k: v for k, v in doc.items() if k in include}

    def find(self, query=None, projection=None):
        # Deduplicate documents. Strategy per doc type:
        # - Users (have 'email' + 'role'): deduplicate by email
        # - Complaints (have 'ticket_no'): deduplicate by ticket_no
        # - Others: deduplicate by _id
        seen: set = set()
        unique_docs = []
        for d in self._docs:
            if "role" in d and "email" in d:
                key = ("user", d["email"])
            elif "ticket_no" in d:
                key = ("complaint", d["ticket_no"])
            else:
                key = ("other", d.get("_id"))
            if key not in seen:
                seen.add(key)
                unique_docs.append(d)
        if not query:
            return [self._project(d, projection) for d in unique_docs]
        return [
            self._project(d, projection)
            for d in unique_docs
            if self._matches(d, query)
        ]

    def find_one(self, query=None):
        if not query:
            return self._docs[0] if self._docs else None
        for d in self._docs:
            if self._matches(d, query):
                return d
        return None


_fallback_collections = {}


def get_collection(name: str = "complaints"):
    """Returns the named collection - real MongoDB if MONGODB_URI is
    configured, otherwise an in-memory fallback for local dev/testing."""
    if MONGODB_URI:
        from pymongo import MongoClient

        client = MongoClient(MONGODB_URI)
        return client[DB_NAME][name]
    if name not in _fallback_collections:
        _fallback_collections[name] = _InMemoryCollection()
    return _fallback_collections[name]
