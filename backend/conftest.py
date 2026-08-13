"""
Root conftest for the Loopline backend test suite.

IMPORTANT: os.environ must be cleaned BEFORE any app module is imported,
because db.py captures MONGODB_URI at module import time:
    MONGODB_URI = os.getenv("MONGODB_URI")   # line 20, db.py
If a real MONGODB_URI is in .env when pytest starts, db.py would point
every test's get_collection() call at the real Atlas cluster, writing
fake test data ("A's private complaint", "My bill was overcharged", etc.)
into production. This has happened — see docs/DECISIONS.md #29.

Stripping MONGODB_URI here (before any import from app.*) forces the
in-memory fallback for the entire test run, regardless of what .env
contains. Tests are always isolated from any real database.
"""
import os
import sys
from pathlib import Path

# Strip real service credentials BEFORE any app module is imported.
# Tests must never touch a real database, Qdrant cluster, or Gemini API.
for _key in ("MONGODB_URI", "QDRANT_URL", "QDRANT_API_KEY", "GEMINI_API_KEY"):
    os.environ.pop(_key, None)

sys.path.insert(0, str(Path(__file__).resolve().parent))
