"""
Lazy-loads and caches banking_complaints.csv as pageable, filterable
complaint records so GET /admin/complaints/baseline can return them
without reading the CSV on every request.

Decision 34 (banking pivot): updated from comcast_complaints.csv to
banking_complaints.csv. Column mapping updated accordingly:
  'complaint'         (was 'Customer Complaint')
  'category'         — already present in banking CSV (CFPB-mapped)
  'date_month_year'  (was 'Date_month_year' / 'Date')
  'state'            (was 'State')
  'received_via'     (was 'Received Via')

Computed once on first request (thread-safe), then held in memory for
the lifetime of the process. The ML models (classify_complaint +
predict_priority) are applied to rows that have no pre-mapped category
so the baseline table shows real Algorithm 1 + Algorithm 2 output.
See docs/DECISIONS.md #28.
"""

import csv
from pathlib import Path
from threading import Lock

_cache: list | None = None
_lock = Lock()

CSV_PATH = Path(__file__).resolve().parent.parent / "data" / "banking_complaints.csv"

STATUS_MAP = {
    "Solved": "Resolved", "Open": "Pending",
    "Closed": "Closed", "Pending": "Pending",
    "Resolved": "Resolved", "In Progress": "In Progress",
}


def _parse_date(raw: str) -> str:
    """Accept ISO 'YYYY-MM-DD' (banking_complaints.csv always uses this)
    and the old 'DD-Mon-YY' format for backward compatibility."""
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
    Blocks on the very first call (a few seconds to classify ~12 k rows
    that don't already have a category) then returns instantly after."""
    global _cache
    if _cache is not None:
        return _cache

    with _lock:
        if _cache is not None:          # double-checked locking
            return _cache

        from .classify import classify_complaint
        from .priority import predict_priority

        rows: list = []
        if not CSV_PATH.exists():
            _cache = rows
            return _cache

        with open(CSV_PATH, newline="", encoding="utf-8") as f:
            for i, row in enumerate(csv.DictReader(f)):
                # banking_complaints.csv uses 'complaint'; legacy uses
                # 'Customer Complaint' — support both for safety.
                text = (
                    row.get("complaint") or
                    row.get("Customer Complaint") or ""
                ).strip()
                if not text:
                    continue

                # Use the pre-mapped CFPB category when present; fall back
                # to Algorithm 1 for any legacy rows without a category col.
                cat = (row.get("category") or "").strip() or classify_complaint(text)
                pri = predict_priority(text, cat)

                status_raw = (row.get("status") or row.get("Status") or "").strip()
                status = STATUS_MAP.get(status_raw, "Pending")

                date_raw = (
                    row.get("date_month_year") or
                    row.get("Date_month_year") or
                    row.get("Date") or ""
                )

                rows.append({
                    "ticket_no": 100001 + i,
                    "user_id": 0,
                    "complaint": text,
                    "category": cat,
                    "priority": pri,
                    "status": status,
                    "date_month_year": _parse_date(date_raw),
                    "time": (row.get("time") or row.get("Time") or "").strip(),
                    "city": (row.get("city") or row.get("City") or "").strip(),
                    "state": (row.get("state") or row.get("State") or "").strip(),
                    "zipcode": (
                        row.get("zipcode") or
                        row.get("Zip code") or ""
                    ).strip(),
                    "received_via": (
                        row.get("received_via") or
                        row.get("Received Via") or
                        "Web Form"
                    ).strip(),
                })

        _cache = rows
        return _cache
