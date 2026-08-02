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
    when the process restarts."""

    def __init__(self):
        self._docs = []
        self._ids = count(1)

    def insert_one(self, doc):
        doc = dict(doc)
        doc["_id"] = next(self._ids)
        self._docs.append(doc)
        return doc

    def find(self, query=None):
        if not query:
            return list(self._docs)
        return [d for d in self._docs if all(d.get(k) == v for k, v in query.items())]

    def find_one(self, query=None):
        results = self.find(query)
        return results[0] if results else None

    def update_one(self, query, update):
        """Only supports the {"$set": {...}} shape - that's all this
        app ever sends. Mirrors pymongo's signature so main.py's code
        works unchanged against either backend; unlike pymongo, this
        returns the updated doc directly rather than an UpdateResult -
        callers here always re-fetch with find_one anyway, so nothing
        currently depends on the return value's shape."""
        match = self.find_one(query)
        if match is None:
            return None
        if "$set" in update:
            match.update(update["$set"])
        return match


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
