"""
Seeds the complaints collection from the banking_complaints.csv on first
startup, but ONLY when running against the in-memory DB fallback (no
MONGODB_URI configured). With a real MongoDB URI the data was already
loaded via `python -m data.load_dataset` as a one-off step, so this
module does nothing in that case.

Decision 34: swapped from comcast_complaints.csv to banking_complaints.csv.
The clean file was produced by backend/data/clean_banking_dataset.py and
contains CFPB-mapped banking complaints with long narratives.

Only runs when:
  - The complaints collection is empty (idempotent - never duplicates)
  - MONGODB_URI is NOT set (in-memory DB mode)
  - The CSV file exists at backend/data/banking_complaints.csv

Does NOT run when MONGODB_URI is set - that environment is assumed to
already have data loaded (or will have it loaded manually).
"""
import csv
import os
from pathlib import Path

CSV_PATH = Path(__file__).resolve().parent.parent / "data" / "banking_complaints.csv"

STATUS_MAP = {
    "Solved": "Resolved",
    "Open": "Pending",
    "Closed": "Closed",
    "Pending": "Pending",
    "Resolved": "Resolved",
    "In Progress": "In Progress",
}


def _normalize_status(raw: str) -> str:
    return STATUS_MAP.get((raw or "").strip(), "Pending")


def _parse_date(raw: str) -> str:
    """Accept ISO 'YYYY-MM-DD' (banking_complaints.csv always uses this)."""
    raw = (raw or "").strip()
    if not raw:
        return ""
    if len(raw) >= 10 and raw[4] == "-":
        return raw[:10]
    # Fallback for any other format
    try:
        from datetime import datetime
        return datetime.strptime(raw, "%m/%d/%Y").strftime("%Y-%m-%d")
    except ValueError:
        return raw


def ensure_dataset_seeded():
    """Called at startup. Seeds complaints from the banking CSV if the
    in-memory collection is empty. Safe to call multiple times."""
    if os.getenv("MONGODB_URI"):
        return  # Real MongoDB - don't auto-seed; data loaded manually

    if not CSV_PATH.exists():
        return  # CSV missing - skip silently

    from .classify import classify_complaint
    from .db import get_collection
    from .priority import predict_priority
    from .tickets import next_ticket_no

    collection = get_collection("complaints")
    if list(collection.find()):
        return  # Already has data

    print(f"[dataset_seed] Seeding complaints from {CSV_PATH.name} (banking pivot)...")
    docs = []
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader):
            text = (row.get("complaint") or "").strip()
            if not text:
                continue
            date_raw = row.get("date_month_year") or ""
            # banking_complaints.csv already has 'category' from CFPB mapping
            category = (row.get("category") or "").strip() or classify_complaint(text)
            docs.append({
                "ticket_no": 100001 + i,
                "user_id": 0,  # 0 = historical, no linked customer account
                "complaint": text,
                "date_month_year": _parse_date(date_raw),
                "time": "00:00:00",
                "city": "",
                "state": (row.get("state") or "").strip(),
                "zipcode": "",
                "received_via": (row.get("received_via") or "Web").strip(),
                "status": _normalize_status(row.get("status") or ""),
                "category": category,
                "priority": "",  # filled below
            })

    # Fill priority after category so predict_priority gets both
    for doc in docs:
        doc["priority"] = predict_priority(doc["complaint"], doc["category"])

    for doc in docs:
        collection.insert_one(doc)

    print(f"[dataset_seed] Seeded {len(docs)} banking complaints — "
          f"dashboard analytics are now populated.")
