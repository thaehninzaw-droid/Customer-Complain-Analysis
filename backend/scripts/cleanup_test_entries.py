"""
Remove test-induced complaint entries from MongoDB Atlas.

Safe-by-default: prints every entry that WOULD be removed and does
nothing else. Pass --delete to actually delete. Never deletes based
solely on "no city" -- always matches on the exact complaint text
from the test files.

Usage (from backend/):
    python scripts/cleanup_test_entries.py           # dry run
    python scripts/cleanup_test_entries.py --delete  # actually delete

Requires: MONGODB_URI in backend/.env
"""
import argparse
import os
import sys
from pathlib import Path

# ── Load .env before any other import ───────────────────────────────────────
for _candidate in [
    Path(__file__).resolve().parent.parent / ".env",
    Path(__file__).resolve().parent.parent.parent / ".env",
]:
    if _candidate.exists():
        try:
            from dotenv import load_dotenv
            load_dotenv(_candidate)
        except ImportError:
            # parse manually if python-dotenv isn't installed
            for line in _candidate.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
        break

MONGODB_URI = os.getenv("MONGODB_URI")
if not MONGODB_URI:
    print("ERROR: MONGODB_URI not set. Add it to backend/.env first.")
    sys.exit(1)

# ── Exact complaint strings produced by the test suite ──────────────────────
# Source: backend/tests/test_api.py and backend/scripts/manual_api_smoke_check.py
# Only include strings that are unambiguously from automated tests,
# not realistic user text that a customer might actually type.
TEST_COMPLAINT_TEXTS = {
    # test_api.py - complaint filing tests
    "My bill was overcharged this month",
    "I have a small question about my invoice, not urgent.",
    "URGENT!!! This is unacceptable, I have been overcharged for weeks and nobody responds, I am furious!",
    "A's private complaint",
    "B's private complaint",
    "totally unrelated text",
    "Customer called about a billing dispute",
    "My internet has been down for three days now.",
    # test_api.py - validation tests (these would be rejected by our current
    # server-side validation, but may be in Atlas from before that was added)
    "too short",
    "short",
    "bad token",
    "no token attached",
    # manual_api_smoke_check.py
    "My internet bill charged me twice this month and nobody will refund it, I'm furious.",
    "My service has been down for three days and nobody has responded.",
    "Manual entry from smoke check - technician never showed up.",
    # manual_api_smoke_check.py (older versions with US cities)
    "Manual entry from smoke test - technician never showed up.",
}

# ── Known test user email patterns ──────────────────────────────────────────
# Users created by the test suite use these patterns. We find their
# user_ids and use them as a secondary match for any complaints we missed.
TEST_EMAIL_PATTERNS = [
    "@example.com",
    "smoketest_",
    "smoke-",
    "test-admin@loopline.io",
    "idempotent-admin@loopline.io",
]


def is_test_email(email: str) -> bool:
    return any(p in (email or "").lower() for p in TEST_EMAIL_PATTERNS)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--delete", action="store_true",
                        help="Actually delete (default: dry run, nothing is changed)")
    parser.add_argument("--db", default=None,
                        help="Database name (default: auto-detected from URI or 'loopline')")
    args = parser.parse_args()

    try:
        from pymongo import MongoClient
    except ImportError:
        print("ERROR: pymongo not installed. Run: pip install pymongo")
        sys.exit(1)

    client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=10_000)
    # Detect DB name from URI or fall back
    # Auto-detect the database name using the same logic and default
    # as app/db.py: env var MONGODB_DB_NAME, defaults to "complaints_db".
    # The cleanup script previously tried to parse the name out of the
    # URI path (which Atlas URIs don't include), fell back to "loopline",
    # and found 0 documents because the real DB is "complaints_db".
    # Fixed to match db.py exactly. See docs/DECISIONS.md #30.
    db_name = args.db or os.getenv("MONGODB_DB_NAME", "complaints_db")

    db = client[db_name]
    complaints_col = db["complaints"]
    users_col = db["users"]

    print(f"Connected to database: {db_name!r}")
    print(f"Total complaints in collection: {complaints_col.count_documents({})}")
    print()

    # ── Pass 1: match by known test complaint text ───────────────────────────
    by_text = list(complaints_col.find(
        {"complaint": {"$in": list(TEST_COMPLAINT_TEXTS)}}
    ))
    print(f"Matched {len(by_text)} entries by test complaint text.")

    # ── Pass 2: find test users then find their complaints ───────────────────
    test_user_ids = set()
    for user in users_col.find():
        if is_test_email(user.get("email", "")):
            test_user_ids.add(user.get("user_id"))

    by_user: list = []
    if test_user_ids:
        by_user = list(complaints_col.find(
            {"user_id": {"$in": list(test_user_ids)}}
        ))
    print(f"Found {len(test_user_ids)} test user(s) → "
          f"{len(by_user)} associated complaint(s).")

    # ── Merge, deduplicate ───────────────────────────────────────────────────
    seen_ids = set()
    to_remove = []
    for c in by_text + by_user:
        oid = str(c["_id"])
        if oid not in seen_ids:
            seen_ids.add(oid)
            to_remove.append(c)

    if not to_remove:
        print("\nNo test-induced entries found. Nothing to do.")
        return

    print(f"\n{'─'*65}")
    print(f"{'DRY RUN' if not args.delete else '⚠ DELETING'}: {len(to_remove)} entries")
    print(f"{'─'*65}")
    for c in sorted(to_remove, key=lambda x: x.get("ticket_no", 0)):
        city_flag = f"  city={c['city']!r}" if c.get("city") else ""
        text_preview = (c.get("complaint") or "")[:55]
        print(f"  #{c.get('ticket_no', '?'):>7}  {c.get('date_month_year', '?')}"
              f"  {text_preview!r}{city_flag}")
    print(f"{'─'*65}")

    if not args.delete:
        print(f"\nDRY RUN complete. Nothing was deleted.")
        print(f"Review the list above, then run with --delete to remove these "
              f"{len(to_remove)} entries.")
        print(f"\n  python scripts/cleanup_test_entries.py --delete")
        return

    # ── Actual delete ────────────────────────────────────────────────────────
    ids = [c["_id"] for c in to_remove]
    result = complaints_col.delete_many({"_id": {"$in": ids}})
    print(f"\nDeleted {result.deleted_count} complaint(s).")

    # Also clean up test users
    if test_user_ids:
        u_result = users_col.delete_many(
            {"user_id": {"$in": list(test_user_ids)}}
        )
        print(f"Deleted {u_result.deleted_count} test user account(s).")

    print(f"\nDone. Remaining complaints: "
          f"{complaints_col.count_documents({})}")


if __name__ == "__main__":
    main()
