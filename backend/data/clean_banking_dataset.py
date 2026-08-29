"""
Cleans the raw CFPB Consumer Complaints CSV and produces:
  backend/data/banking_complaints.csv  -- the ONLY file used by
                                          load_dataset.py, dataset_seed.py,
                                          and both training scripts.

Usage:
    python -m data.clean_banking_dataset [path/to/raw/consumer_complaints.csv]

If no path is given, looks for:
    backend/data/raw/consumer_complaints.csv

The raw file is NEVER modified.

Cleaning steps (all counts logged):
  1. Read with utf-8-sig (BOM-safe).
  2. Normalise column names to a canonical schema.
  3. Drop rows with missing / blank narrative.
  4. Drop rows whose narrative length < MIN_NARRATIVE_LEN (200 chars).
  5. Strip / collapse whitespace; replace CFPB redaction tokens (XXXX) with [REDACTED].
  6. Parse dates to ISO YYYY-MM-DD; drop unparseable dates.
  7. Map Product -> 5 banking categories; drop rows that cannot be mapped
     (unmappable products are sent to 'Other banking').
  8. Drop exact-duplicate narratives (keep first).
  9. Drop duplicate Complaint IDs (keep first).
 10. Balance: undersample Credit reporting & Debt collection if they exceed
     MAX_PER_CLASS so that no single class is more than 3× the median.
 11. Write banking_complaints.csv with stable column order.
     Columns: complaint, category, product_raw, date_month_year,
              state, received_via, issue, company, source

Run after every raw-file update; output is deterministic given the same input.
"""

import csv
import re
import sys
from datetime import datetime
from pathlib import Path
from collections import Counter

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
MIN_NARRATIVE_LEN = 200          # advisor explicitly wants long narratives
MAX_PER_CLASS = 3000             # cap dominant classes before training
RANDOM_SEED = 42

# CFPB Product -> 5 banking categories
PRODUCT_MAP = {
    # Cards
    "Credit card": "Cards",
    "Prepaid card": "Cards",
    "Credit card or prepaid card": "Cards",
    # Accounts
    "Checking or savings account": "Accounts",
    "Bank account or service": "Accounts",
    "Money transfers": "Accounts",
    "Money transfer, virtual currency, or money service": "Accounts",
    "Virtual currency": "Accounts",
    # Loans
    "Mortgage": "Loans",
    "Student loan": "Loans",
    "Payday loan": "Loans",
    "Consumer Loan": "Loans",
    "Vehicle loan or lease": "Loans",
    "Payday loan, title loan, or personal loan": "Loans",
    "Other financial service": "Loans",
    # Collections & Credit reporting
    "Debt collection": "Collections & Credit reporting",
    "Credit reporting": "Collections & Credit reporting",
    "Credit reporting, credit repair services, or other personal consumer reports": "Collections & Credit reporting",
}
DEFAULT_CATEGORY = "Other banking"

REDACT_RE = re.compile(r'\bXX+\b')  # XXXX, XX, XXXXXXXXXXXX …

OUTPUT_COLUMNS = [
    "complaint", "category", "product_raw",
    "date_month_year", "state", "received_via",
    "issue", "company", "source",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalise_narrative(text: str) -> str:
    """Strip, collapse whitespace, normalise newlines, replace CFPB tokens."""
    text = text.strip()
    text = REDACT_RE.sub("[REDACTED]", text)
    text = re.sub(r"[\r\n]+", " ", text)
    text = re.sub(r" {2,}", " ", text)
    return text


def _parse_date(raw: str) -> str:
    """Return YYYY-MM-DD or '' if unparseable."""
    raw = (raw or "").strip()
    if not raw:
        return ""
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%d-%b-%y", "%d-%m-%Y"):
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return ""


def _map_product(product: str) -> str:
    product = (product or "").strip()
    return PRODUCT_MAP.get(product, DEFAULT_CATEGORY)


def _log(msg: str):
    print(f"[clean_banking_dataset] {msg}")


# ---------------------------------------------------------------------------
# Main cleaning function
# ---------------------------------------------------------------------------

def clean(raw_path: Path, out_path: Path):
    _log(f"Reading raw file: {raw_path}")

    with open(raw_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        raw_rows = list(reader)

    count_raw = len(raw_rows)
    _log(f"Step 0 — Raw rows: {count_raw:,}")

    # -----------------------------------------------------------------------
    # Step 3: Drop rows with missing/blank narrative
    # -----------------------------------------------------------------------
    rows = [r for r in raw_rows if (r.get("Consumer complaint narrative") or "").strip()]
    count_after_narrative = len(rows)
    _log(f"Step 3 — After dropping empty narratives: {count_after_narrative:,}  "
         f"(dropped {count_raw - count_after_narrative:,})")

    # -----------------------------------------------------------------------
    # Step 4: Drop rows with narrative shorter than MIN_NARRATIVE_LEN
    # -----------------------------------------------------------------------
    rows = [r for r in rows if len((r.get("Consumer complaint narrative") or "").strip()) >= MIN_NARRATIVE_LEN]
    count_after_length = len(rows)
    _log(f"Step 4 — After length filter (>= {MIN_NARRATIVE_LEN} chars): {count_after_length:,}  "
         f"(dropped {count_after_narrative - count_after_length:,})")

    # -----------------------------------------------------------------------
    # Step 5: Normalise narrative text
    # -----------------------------------------------------------------------
    for r in rows:
        r["_narrative_clean"] = _normalise_narrative(r["Consumer complaint narrative"])

    # -----------------------------------------------------------------------
    # Step 6: Parse dates; drop unparseable
    # -----------------------------------------------------------------------
    rows_pre_date = len(rows)
    rows_out = []
    for r in rows:
        d = _parse_date(r.get("Date received", ""))
        if d:
            r["_date_parsed"] = d
            rows_out.append(r)
    rows = rows_out
    count_after_date = len(rows)
    _log(f"Step 6 — After date parse: {count_after_date:,}  "
         f"(dropped {rows_pre_date - count_after_date:,})")

    # -----------------------------------------------------------------------
    # Step 7: Map Product -> category
    # -----------------------------------------------------------------------
    for r in rows:
        r["_category"] = _map_product(r.get("Product", ""))

    # Product distribution before dedupe
    product_dist = Counter(r.get("Product", "") for r in rows)
    cat_dist_pre = Counter(r["_category"] for r in rows)
    _log(f"Step 7 — Category distribution after mapping: {dict(cat_dist_pre)}")

    # -----------------------------------------------------------------------
    # Step 8: Drop exact-duplicate narratives
    # -----------------------------------------------------------------------
    seen_narratives = set()
    unique_rows = []
    for r in rows:
        n = r["_narrative_clean"]
        if n not in seen_narratives:
            seen_narratives.add(n)
            unique_rows.append(r)
    rows = unique_rows
    count_after_dedupe_text = len(rows)
    _log(f"Step 8 — After deduplicating narratives: {count_after_dedupe_text:,}")

    # -----------------------------------------------------------------------
    # Step 9: Drop duplicate Complaint IDs
    # -----------------------------------------------------------------------
    seen_ids = set()
    unique_id_rows = []
    for r in rows:
        cid = r.get("Complaint ID", "")
        if cid not in seen_ids:
            seen_ids.add(cid)
            unique_id_rows.append(r)
    rows = unique_id_rows
    count_after_dedupe_id = len(rows)
    _log(f"Step 9 — After deduplicating Complaint IDs: {count_after_dedupe_id:,}")

    # -----------------------------------------------------------------------
    # Step 10: Balance — undersample classes that exceed MAX_PER_CLASS
    # -----------------------------------------------------------------------
    from random import Random
    rng = Random(RANDOM_SEED)
    by_cat = {}
    for r in rows:
        by_cat.setdefault(r["_category"], []).append(r)

    balanced = []
    for cat, cat_rows in by_cat.items():
        if len(cat_rows) > MAX_PER_CLASS:
            sampled = rng.sample(cat_rows, MAX_PER_CLASS)
            _log(f"Step 10 — Undersampled '{cat}': {len(cat_rows):,} -> {MAX_PER_CLASS}")
            balanced.extend(sampled)
        else:
            _log(f"Step 10 — Kept '{cat}' as-is: {len(cat_rows):,}")
            balanced.extend(cat_rows)

    rows = balanced
    count_final = len(rows)
    _log(f"Step 10 — After balancing: {count_final:,}")

    # Final category distribution
    cat_dist_final = Counter(r["_category"] for r in rows)
    _log(f"Final category distribution: {dict(cat_dist_final)}")

    # -----------------------------------------------------------------------
    # Step 11: Write output CSV
    # -----------------------------------------------------------------------
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        for r in rows:
            writer.writerow({
                "complaint": r["_narrative_clean"],
                "category": r["_category"],
                "product_raw": (r.get("Product") or "").strip(),
                "date_month_year": r["_date_parsed"],
                "state": (r.get("State") or "").strip(),
                "received_via": (r.get("Submitted via") or "Web").strip(),
                "issue": (r.get("Issue") or "").strip(),
                "company": (r.get("Company") or "").strip(),
                "source": "cfpb_kaggle",
            })

    _log(f"Wrote {count_final:,} rows to {out_path}")

    # -----------------------------------------------------------------------
    # Print waterfall summary (also used by EDA.md writer)
    # -----------------------------------------------------------------------
    return {
        "raw_path": str(raw_path),
        "out_path": str(out_path),
        "count_raw": count_raw,
        "count_after_narrative": count_after_narrative,
        "count_after_length": count_after_length,
        "count_after_date": count_after_date,
        "count_after_dedupe_text": count_after_dedupe_text,
        "count_after_dedupe_id": count_after_dedupe_id,
        "count_final": count_final,
        "product_dist": dict(product_dist.most_common(20)),
        "cat_dist_pre": dict(cat_dist_pre),
        "cat_dist_final": dict(cat_dist_final),
        "min_narrative_len": MIN_NARRATIVE_LEN,
        "max_per_class": MAX_PER_CLASS,
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    DATA_DIR = Path(__file__).resolve().parent
    if len(sys.argv) > 1:
        raw_path = Path(sys.argv[1])
    else:
        raw_path = DATA_DIR / "raw" / "consumer_complaints.csv"

    if not raw_path.exists():
        print(f"ERROR: raw file not found at {raw_path}")
        print("Download the CFPB Consumer Complaints dataset from Kaggle:")
        print("  https://www.kaggle.com/datasets/sebastienverpile/consumercomplaintsdata")
        print("and place it at backend/data/raw/consumer_complaints.csv")
        sys.exit(1)

    out_path = DATA_DIR / "banking_complaints.csv"
    stats = clean(raw_path, out_path)

    print("\n=== WATERFALL SUMMARY ===")
    print(f"Raw rows:                    {stats['count_raw']:>10,}")
    print(f"After drop empty narrative:  {stats['count_after_narrative']:>10,}  (dropped {stats['count_raw']-stats['count_after_narrative']:,})")
    print(f"After length filter (≥{stats['min_narrative_len']} c): {stats['count_after_length']:>10,}  (dropped {stats['count_after_narrative']-stats['count_after_length']:,})")
    print(f"After date parse:            {stats['count_after_date']:>10,}  (dropped {stats['count_after_length']-stats['count_after_date']:,})")
    print(f"After narrative dedupe:      {stats['count_after_dedupe_text']:>10,}  (dropped {stats['count_after_date']-stats['count_after_dedupe_text']:,})")
    print(f"After ID dedupe:             {stats['count_after_dedupe_id']:>10,}  (dropped {stats['count_after_dedupe_text']-stats['count_after_dedupe_id']:,})")
    print(f"After balancing (max {stats['max_per_class']:,}/cat): {stats['count_final']:>10,}")
    print(f"\nFinal category distribution: {stats['cat_dist_final']}")
    print(f"\nOutput: {stats['out_path']}")
