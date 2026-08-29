"""
Loads the banking_complaints.csv (or any CSV with a similar shape)
into the complaints collection, running each row through the same
classifier + priority predictor the API uses (Algorithm 1 + Algorithm 2)
- so historical and new complaints end up tagged the same way.

Decision 34: primary dataset changed from comcast_complaints.csv to
banking_complaints.csv (CFPB-mapped banking data). The loader supports
both column schemas for backward compatibility.

Usage:
    python -m data.load_dataset path/to/banking_complaints.csv
    python -m data.load_dataset path/to/banking_complaints.csv --demo-shift-dates

Expected columns (banking_complaints.csv - clean CFPB banking data):
    complaint, category, product_raw, date_month_year, state,
    received_via, issue, company, source

Legacy columns also accepted (comcast_complaints.csv):
    Customer Complaint, Date_month_year, Time, Received Via,
    City, State, Zip code, Status

The 'category' column in banking_complaints.csv already contains the
CFPB-mapped category - no re-classification needed for that field.
Historical rows get user_id = 0.

DATE FORMAT: banking_complaints.csv uses ISO "YYYY-MM-DD" in
date_month_year, which is exactly what this app stores everywhere.
parse_date() handles multiple formats for backward compatibility.

STATUS VOCABULARY: banking_complaints.csv has no 'status' column
(CFPB data has no status). These rows default to "Pending". The
legacy Comcast CSV uses "Solved"/"Open" - mapped as before.

The BOM at the start of the CSV header is handled by utf-8-sig encoding.
"""

import csv
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.classify import classify_complaint  # noqa: E402
from app.db import get_collection  # noqa: E402
from app.priority import predict_priority  # noqa: E402
from app.tickets import next_ticket_no  # noqa: E402

STATUS_MAP = {
    "Solved": "Resolved",
    "Open": "Pending",
    "Closed": "Closed",
    "Pending": "Pending",
    "Resolved": "Resolved",       # already-normalized value, pass through
    "In Progress": "In Progress",  # already-normalized value, pass through
}


def normalize_status(raw: str) -> str:
    return STATUS_MAP.get((raw or "").strip(), "Pending")


def parse_date(raw_date: str):
    """Returns a datetime.date, or None if every known format fails to
    parse. Split out from normalize_date() (below) so --demo-shift-dates
    can work with real date objects (to compute/apply a day offset)
    rather than re-parsing formatted strings."""
    raw_date = (raw_date or "").strip()
    for fmt in ("%d-%m-%y", "%Y-%m-%d", "%d-%b-%y"):
        try:
            return datetime.strptime(raw_date, fmt).date()
        except ValueError:
            continue
    return None


def normalize_date(raw_date: str) -> str:
    """Converts the Kaggle CSV's "DD-MM-YY" date to this app's
    "YYYY-MM-DD" format. Falls back to today's date string if parsing
    fails, rather than storing an unparseable value that would
    silently vanish from the monthly-volume chart (see module
    docstring, point 1)."""
    parsed = parse_date(raw_date)
    return (parsed or date.today()).strftime("%Y-%m-%d")


def normalize_time(raw_time: str) -> str:
    """Converts "3:53:50 PM" (12-hour, the Kaggle CSV's format) to
    "15:53:50" (24-hour, this app's format elsewhere). Not load-
    bearing for anything today (nothing parses `time` the way
    `date_month_year` gets parsed for analytics), but kept consistent
    on principle - an inconsistent format here is exactly the kind of
    thing that causes a confusing bug once someone DOES build
    something that reads it."""
    raw_time = (raw_time or "").strip()
    for fmt in ("%I:%M:%S %p", "%H:%M:%S"):
        try:
            return datetime.strptime(raw_time, fmt).strftime("%H:%M:%S")
        except ValueError:
            continue
    return raw_time  # unrecognized format - keep as-is rather than lose it


def compute_demo_shift(raw_dates) -> timedelta:
    """Returns the timedelta that, added to every parseable date in
    `raw_dates`, makes the LATEST one land on today. A single shared
    day-offset (not a "just change the year" remap) so every complaint
    keeps its exact relative spacing to every other one - the real
    dataset's busiest-month pattern (see docs/ALGORITHMS.md's "June
    2015" finding) shifts intact, just relabeled to a recent-feeling
    window. Falls back to a zero shift if nothing parses."""
    parsed = [d for d in (parse_date(r) for r in raw_dates) if d is not None]
    if not parsed:
        return timedelta(0)
    return date.today() - max(parsed)


def load_csv(path: str, demo_shift_dates: bool = False) -> int:
    collection = get_collection("complaints")
    # Track the running max ticket_no locally instead of re-querying
    # the whole collection on every row (that was O(n^2) for a ~2000+
    # row import - fine at small scale but no reason to keep it now
    # that this file's being touched anyway).
    existing_ticket_nos = [c["ticket_no"] for c in collection.find()]
    next_no = next_ticket_no(existing_ticket_nos)

    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    shift = timedelta(0)
    if demo_shift_dates:
        shift = compute_demo_shift([r.get("Date", "") for r in rows])
        print(f"[load_dataset] --demo-shift-dates: shifting every date by {shift.days} days "
              f"(demo/presentation only - the real analysis period is unchanged, see docs/ALGORITHMS.md)")

    count = 0
    for row in rows:
        # Support banking CSV ('complaint') and legacy CSV ('Customer Complaint')
        text = (row.get("complaint") or row.get("Customer Complaint") or "").strip()
        if not text:
            continue

        # Use pre-mapped category from banking_complaints.csv when available;
        # fall back to classifier for legacy CSV without a category column.
        existing_category = (row.get("category") or "").strip()
        category = existing_category if existing_category else classify_complaint(text)
        priority = predict_priority(text, category)

        received_via = row.get("received_via") or row.get("Received Via") or "Web Form"

        # Banking CSV has 'date_month_year'; legacy CSV has 'Date'
        raw_date = (row.get("date_month_year") or row.get("Date_month_year") or
                    row.get("Date") or "")
        parsed_date = parse_date(raw_date)
        effective_date = (parsed_date or date.today()) + shift

        doc = {
            "ticket_no": next_no,
            "user_id": 0,
            "category": category,
            "priority": priority,
            "complaint": text,
            "date_month_year": effective_date.strftime("%Y-%m-%d"),
            "time": normalize_time(row.get("Time", "")),
            "city": row.get("city") or row.get("City") or None,
            "state": row.get("state") or row.get("State") or None,
            "zipcode": row.get("zipcode") or row.get("Zip code") or None,
            "status": normalize_status(row.get("status") or row.get("Status") or ""),
            "received_via": received_via,
            "source": row.get("source") or ("kaggle_import" if not demo_shift_dates else "kaggle_import_demo_shifted"),
        }
        collection.insert_one(doc)
        next_no += 1
        count += 1
    print(f"Loaded {count} complaints from {path}")
    return count


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    demo_flag = "--demo-shift-dates" in sys.argv
    if len(args) != 1:
        print("Usage: python -m data.load_dataset path/to/comcast_complaints.csv [--demo-shift-dates]")
        sys.exit(1)
    load_csv(args[0], demo_shift_dates=demo_flag)
