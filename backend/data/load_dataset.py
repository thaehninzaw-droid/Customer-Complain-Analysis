"""
Loads the Comcast Telecom Complaints CSV (or any CSV with a similar
shape) into the complaints collection, running each row through the
same classifier + priority predictor the API uses (Algorithm 1 +
Algorithm 2) - so historical and new complaints end up tagged the
same way.

Usage:
    python -m data.load_dataset path/to/comcast_complaints.csv
    python -m data.load_dataset path/to/comcast_complaints.csv --demo-shift-dates

Expected columns (from the original Kaggle dataset):
    Ticket #, Customer Complaint, Date, Date_month_year, Time,
    Received Via, City, State, Zip code, Status,
    Filing on Behalf of Someone

Only "Customer Complaint" is required - everything else is optional
and mapped onto the app's own field names (ticket_no, date_month_year,
etc.) where available. Historical rows get user_id = 0 (no signed-up
customer filed them).

Works unchanged against the SYNTHETIC dataset (data/generate_synthetic_
dataset.py) or the real Kaggle CSV - same column names either way (see
docs/ALGORITHMS.md) - but see the two normalization steps below, both
found by actually running this against the real downloaded dataset
rather than assumed to be unnecessary:

1. DATE FORMAT: the real CSV's "Date" column is "DD-MM-YY"
   (e.g. "22-04-15" = 22 April 2015) - but this app's own
   `date_month_year` field is stored as "YYYY-MM-DD" everywhere else
   (see app/main.py's create_complaint). app/analytics.py parses
   `date_month_year` as `s[0:4]` for year / `s[5:7]` for month to build
   the monthly-volume chart - fed the raw "22-04-15" directly, EVERY
   row from a real import would silently fail that parse (caught by a
   try/except, so nothing crashes - it would just make the monthly
   volume chart show zero historical data, which defeats the point of
   loading history in the first place). Converted below.

2. STATUS VOCABULARY: the real CSV uses "Solved"/"Open" instead of
   this app's "Resolved"/"Pending" - mapped below so a single, mixed-
   source complaints collection has one consistent status vocabulary
   (the alternative - teaching every place that checks "is this
   resolved" about a second set of synonyms - is worse; see
   docs/ALGORITHMS.md).

The BOM at the start of the real CSV's header row (a Kaggle/Excel
export artifact) is handled by the utf-8-sig encoding below - it only
ever corrupted the "Ticket #" column's key in practice, which this
loader doesn't read anyway (fresh sequential ticket numbers are always
generated instead), but utf-8-sig is the correct fix regardless.

--demo-shift-dates (optional): shifts every row's date forward by a
fixed number of days so the most recent complaint in the dataset lands
on today - see DECISIONS.md #19 for the full reasoning. Off by default.
The real dataset file on disk is never modified by this flag; it only
affects what gets written into whichever database this script targets.
Never cite demo-shifted dates as real historical data - the true dates
are 2015, see docs/ALGORITHMS.md for the actual analysis period.
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
        text = (row.get("Customer Complaint") or "").strip()
        if not text:
            continue

        category = classify_complaint(text)
        priority = predict_priority(text, category)
        # Deliberately NOT normalized to match the app's "Web Form"/
        # "Manual Entry" vocabulary - see module docstring point 2's
        # sibling discussion in docs/ALGORITHMS.md for why real
        # historical values ("Internet", "Customer Care Call") are
        # kept as-is rather than silently relabeled.
        received_via = row.get("Received Via") or "Web Form"

        parsed_date = parse_date(row.get("Date", ""))
        effective_date = (parsed_date or date.today()) + shift

        doc = {
            "ticket_no": next_no,
            "user_id": 0,
            "category": category,
            "priority": priority,
            "complaint": text,
            "date_month_year": effective_date.strftime("%Y-%m-%d"),
            "time": normalize_time(row.get("Time", "")),
            "city": row.get("City") or None,
            "state": row.get("State") or None,
            "zipcode": row.get("Zip code") or None,
            "status": normalize_status(row.get("Status", "")),
            "received_via": received_via,
            "source": "kaggle_import" if not demo_shift_dates else "kaggle_import_demo_shifted",
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
