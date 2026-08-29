"""
One-off: rewrite live complaint categories that still use old
Comcast labels (Billing, Technical, Service, Financial, Others).

Does NOT delete tickets or users.
Does NOT touch banking_complaints.csv / baseline.

From backend/:
    python -m data.remap_live_categories

Needs MONGODB_URI. In-memory mode cannot be patched from a
second process — restart the server instead.
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.categories import CATEGORIES
from app.classify import classify_complaint
from app.db import get_collection


def main():
    if not os.getenv("MONGODB_URI"):
        print("No MONGODB_URI. In-memory DB cannot be remapped from here.")
        print("Stop uvicorn and start it again, or set MONGODB_URI.")
        return 1

    col = get_collection("complaints")
    docs = list(col.find())
    changed = 0
    skipped = 0
    for d in docs:
        old = (d.get("category") or "").strip()
        if old in CATEGORIES:
            skipped += 1
            continue
        new = classify_complaint(d.get("complaint") or "")
        col.update_one({"ticket_no": d["ticket_no"]}, {"$set": {"category": new}})
        print(f"#{d.get('ticket_no')}  {old!r} -> {new}")
        changed += 1

    print(f"Updated {changed}  already-ok {skipped}  total {len(docs)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
