"""
Lazy-loads banking_complaints.csv for GET /admin/complaints/baseline
and GET /admin/analytics/baseline.

Do NOT run the trained XGBoost / Logistic Regression models on all
12,000 rows at request time. That is what froze the dashboard.

- category: use the CFPB-mapped column already in the CSV
- priority: cheap lexicon baseline only (no sklearn / xgboost)
- status: CSV status if present, else Pending
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
    raw = (raw or "").strip()
    if len(raw) >= 10 and raw[4] == "-":
        return raw[:10]
    try:
        from datetime import datetime
        return datetime.strptime(raw, "%d-%b-%y").strftime("%Y-%m-%d")
    except ValueError:
        try:
            from datetime import datetime
            return datetime.strptime(raw, "%m/%d/%Y").strftime("%Y-%m-%d")
        except ValueError:
            return raw


def get_baseline() -> list:
    global _cache
    if _cache is not None:
        return _cache

    with _lock:
        if _cache is not None:
            return _cache

        # Lexicon only — must not import predict_priority() here.
        from .priority import predict_priority_baseline

        rows: list = []
        if not CSV_PATH.exists():
            _cache = rows
            return _cache

        with open(CSV_PATH, newline="", encoding="utf-8-sig") as f:
            for i, row in enumerate(csv.DictReader(f)):
                text = (
                    row.get("complaint") or
                    row.get("Customer Complaint") or ""
                ).strip()
                if not text:
                    continue

                cat = (row.get("category") or "").strip() or "Other banking"
                status_raw = (row.get("status") or row.get("Status") or "").strip()
                status = STATUS_MAP.get(status_raw, "Pending") if status_raw else "Pending"
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
                    "priority": predict_priority_baseline(text),
                    "status": status,
                    "date_month_year": _parse_date(date_raw),
                    "time": (row.get("time") or row.get("Time") or "").strip(),
                    "city": (row.get("city") or row.get("City") or "").strip(),
                    "state": (row.get("state") or row.get("State") or "").strip(),
                    "zipcode": (row.get("zipcode") or row.get("Zip code") or "").strip(),
                    "received_via": (
                        row.get("received_via") or
                        row.get("Received Via") or
                        "Web Form"
                    ).strip(),
                })

        _cache = rows
        return _cache
