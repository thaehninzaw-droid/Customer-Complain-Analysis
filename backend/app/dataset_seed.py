"""
Seeds the complaints collection from the Comcast dataset CSV on first
startup, but ONLY when running against the in-memory DB fallback (no
MONGODB_URI configured). With a real MongoDB URI the data was already
loaded via `python -m data.load_dataset` as a one-off step, so this
module does nothing in that case.

This is what makes the admin dashboard show real analytics (charts,
counts, category/priority/status breakdowns) immediately after cloning
and running `uvicorn app.main:app` for the first time, without any
separate data-loading step. Without it, the dashboard is empty and the
charts have nothing to render - which was the exact problem on first
run with a fresh in-memory DB (see docs/DECISIONS.md #26).

Only runs when:
  - The complaints collection is empty (idempotent - never duplicates)
  - MONGODB_URI is NOT set (in-memory DB mode)
  - The CSV file exists at backend/data/comcast_complaints.csv

Does NOT run when MONGODB_URI is set - that environment is assumed to
already have data loaded (or will have it loaded manually).
"""
import csv
import os
from pathlib import Path

CSV_PATH = Path(__file__).resolve().parent.parent / "data" / "comcast_complaints.csv"

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
    """Accept both ISO 'YYYY-MM-DD' and old 'DD-Mon-YY' format."""
    raw = (raw or "").strip()
    if not raw:
        return ""
    if len(raw) >= 10 and raw[4] == "-":
        return raw[:10]
    # Old format e.g. '22-Apr-15'
    try:
        from datetime import datetime
        return datetime.strptime(raw, "%d-%b-%y").strftime("%Y-%m-%d")
    except ValueError:
        return raw


def ensure_dataset_seeded():
    """Called at startup. Seeds complaints from the CSV if the
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

    print(f"[dataset_seed] Seeding complaints from {CSV_PATH.name}...")
    docs = []
    with open(CSV_PATH, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader):
            text = (row.get("Customer Complaint") or "").strip()
            if not text:
                continue
            date_raw = row.get("Date_month_year") or row.get("Date") or ""
            docs.append({
                "ticket_no": 100001 + i,
                "user_id": 0,  # 0 = historical, no linked customer account
                "complaint": text,
                "date_month_year": _parse_date(date_raw),
                "time": (row.get("Time") or "00:00:00").strip(),
                "city": (row.get("City") or "").strip(),
                "state": (row.get("State") or "").strip(),
                "zipcode": (row.get("Zip code") or "").strip(),
                "received_via": (row.get("Received Via") or "Web Form").strip(),
                "status": _normalize_status(row.get("Status") or ""),
                "category": classify_complaint(text),
                "priority": "",  # filled below
            })

    # Fill priority after category so predict_priority gets both
    for doc in docs:
        doc["priority"] = predict_priority(doc["complaint"], doc["category"])

    for doc in docs:
        collection.insert_one(doc)

    print(f"[dataset_seed] Seeded {len(docs)} complaints — "
          f"dashboard analytics are now populated.")
