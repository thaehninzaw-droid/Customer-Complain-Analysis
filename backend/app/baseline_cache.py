"""
Lazy-loads and caches the Comcast CSV as pageable, filterable complaint
records so GET /admin/complaints/baseline can return them without
reading the CSV on every request.

Computed once on first request (thread-safe), then held in memory for
the lifetime of the process. The same ML models used for live complaints
(classify_complaint + predict_priority) are applied to every row so the
baseline table shows real Algorithm 1 + Algorithm 2 output, not just
raw CSV text. See docs/DECISIONS.md #28.
"""

import csv
from pathlib import Path
from threading import Lock

_cache: list | None = None
_lock = Lock()

CSV_PATH = Path(__file__).resolve().parent.parent / "data" / "comcast_complaints.csv"

STATUS_MAP = {
    "Solved": "Resolved", "Open": "Pending",
    "Closed": "Closed", "Pending": "Pending",
    "Resolved": "Resolved", "In Progress": "In Progress",
}


def _parse_date(raw: str) -> str:
    """Accept both ISO 'YYYY-MM-DD' and old 'DD-Mon-YY' format."""
    raw = (raw or "").strip()
    if len(raw) >= 10 and raw[4] == "-":
        return raw[:10]
    try:
        from datetime import datetime
        return datetime.strptime(raw, "%d-%b-%y").strftime("%Y-%m-%d")
    except ValueError:
        return raw


def get_baseline() -> list:
    """Returns the cached list of baseline complaint dicts.
    Blocks on the very first call (a few seconds to classify 2224 rows)
    then returns instantly on subsequent calls."""
    global _cache
    if _cache is not None:
        return _cache

    with _lock:
        if _cache is not None:  # double-checked locking
            return _cache

        # Import here so the module-level import doesn't run at startup
        from .classify import classify_complaint
        from .priority import predict_priority

        rows = []
        if not CSV_PATH.exists():
            _cache = rows
            return _cache

        with open(CSV_PATH, newline="", encoding="utf-8-sig") as f:
            for i, row in enumerate(csv.DictReader(f)):
                text = (row.get("Customer Complaint") or "").strip()
                if not text:
                    continue
                cat = classify_complaint(text)
                pri = predict_priority(text, cat)
                status = STATUS_MAP.get((row.get("Status") or "").strip(), "Pending")
                date_raw = row.get("Date_month_year") or row.get("Date") or ""
                rows.append({
                    "ticket_no": 100001 + i,
                    "user_id": 0,
                    "complaint": text,
                    "category": cat,
                    "priority": pri,
                    "status": status,
                    "date_month_year": _parse_date(date_raw),
                    "time": (row.get("Time") or "").strip(),
                    "city": (row.get("City") or "").strip(),
                    "state": (row.get("State") or "").strip(),
                    "zipcode": (row.get("Zip code") or "").strip(),
                    "received_via": (row.get("Received Via") or "Web Form").strip(),
                })

        _cache = rows
        return _cache
