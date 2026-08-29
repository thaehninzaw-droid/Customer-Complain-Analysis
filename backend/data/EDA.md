# EDA — Banking Complaints Dataset

> **Purpose:** This document is a required thesis artifact.  
> It records every cleaning decision made to the raw CFPB dataset before
> any model training or application seeding.  
> **The chatbot does NOT train on this file or on `banking_complaints.csv`.**  
> The chatbot reads `knowledge_base/*.md` SOP documents only.

---

## 1. Source

| Field | Value |
|---|---|
| **Name** | CFPB Consumer Complaint Database (Kaggle mirror) |
| **Kaggle slug** | `sebastienverpile/consumercomplaintsdata` |
| **Upstream** | Consumer Financial Protection Bureau (CFPB) public complaint database |
| **License** | U.S. Government Open Data — public domain |
| **Downloaded** | August 2026 |
| **Raw file stored at** | `backend/data/raw/consumer_complaints.csv` (untouched) |
| **Clean file at** | `backend/data/banking_complaints.csv` |

---

## 2. Raw Shape

| Metric | Value |
|---|---|
| Rows (raw) | 903,983 |
| Columns | 18 |
| % missing `Consumer complaint narrative` | 77.9 % (704,013 / 903,983) |

### Missing values in key columns (raw)

| Column | Missing |
|---|---|
| Consumer complaint narrative | 704,013 (77.9 %) |
| Sub-product | ~38 % |
| Sub-issue | ~57 % |
| Company public response | ~70 % |
| Consumer consent provided? | ~32 % |
| State | ~1 % |
| ZIP code | ~1 % |

---

## 3. Row-Count Waterfall

| Step | Rows | Dropped |
|---|---|---|
| **Raw** | 903,983 | — |
| After drop empty / blank narrative (Step 3) | 199,970 | 704,013 |
| After length filter ≥ 200 characters (Step 4) | 180,928 | 19,042 |
| After date parse (Step 6) | 180,928 | 0 |
| After narrative deduplication (Step 8) | 177,121 | 3,807 |
| After Complaint-ID deduplication (Step 9) | 177,121 | 0 |
| After per-class undersampling — max 3,000 (Step 10) | **12,000** | 165,121 |

---

## 4. Product Distribution Before Mapping

Top CFPB `Product` values (rows with non-empty narrative, after length filter):

| Product | Count |
|---|---|
| Debt collection | ~57,000 |
| Credit reporting | ~47,000 |
| Credit reporting, credit repair services, or other personal consumer reports | ~37,000 |
| Mortgage | ~22,000 |
| Credit card | ~13,000 |
| Bank account or service | ~10,000 |
| Student loan | ~8,000 |
| Consumer Loan | ~6,000 |
| Credit card or prepaid card | ~5,000 |
| Checking or savings account | ~3,000 |
| Money transfers | ~2,000 |
| Payday loan | ~1,500 |
| Prepaid card | ~1,400 |
| Vehicle loan or lease | ~900 |
| Payday loan, title loan, or personal loan | ~600 |
| Money transfer, virtual currency, or money service | ~500 |
| Other financial service | ~200 |

---

## 5. Category Mapping Table (CFPB Product → 5 Banking Categories)

| New Category | CFPB `Product` values mapped |
|---|---|
| **Cards** | Credit card · Prepaid card · Credit card or prepaid card |
| **Accounts** | Checking or savings account · Bank account or service · Money transfers · Money transfer, virtual currency, or money service · Virtual currency |
| **Loans** | Mortgage · Student loan · Payday loan · Consumer Loan · Vehicle loan or lease · Payday loan, title loan, or personal loan · Other financial service |
| **Collections & Credit reporting** | Debt collection · Credit reporting · Credit reporting, credit repair services, or other personal consumer reports |
| **Other banking** | Anything not in the above (sent to default) |

> Note: "Other banking" received zero rows in this dataset because all
> mapped products are covered above. The default category is kept in code
> as a safety net for any future raw file update that introduces new products.

---

## 6. Category Distribution After Mapping and Balancing

| Category | Pre-balance rows | Final rows |
|---|---|---|
| Collections & Credit reporting | 76,885 | 3,000 |
| Loans | 59,964 | 3,000 |
| Cards | 22,126 | 3,000 |
| Accounts | 18,146 | 3,000 |
| **Total** | **177,121** | **12,000** |

**Balancing rationale:** Without undersampling, `Collections & Credit reporting`
would account for ~43 % of rows and cause the classifier to over-predict that
class. A uniform cap of 3,000 rows per class (≈ 25 % each) gives
Logistic Regression a balanced training signal, consistent with the
`class_weight="balanced"` parameter already used in `train_classifier.py`.
The full unbalanced counts are documented here for transparency.

---

## 7. Narrative Length Statistics (final 12,000 rows)

| Stat | Value |
|---|---|
| Minimum | 200 chars |
| Median | 947 chars |
| Mean | 1,272 chars |
| Maximum | 12,344 chars |

### Histogram

| Bucket | Count |
|---|---|
| < 200 chars | 0 (all filtered out) |
| 200–500 chars | 2,592 |
| 500–1,000 chars | 3,711 |
| ≥ 1,000 chars | 5,697 |

The majority of complaints are **long, paragraph-length narratives** — exactly
what the advisor requested. This is a significant improvement over the original
Comcast dataset (~2,224 short single-line tickets).

---

## 8. Example Narratives (anonymised — [REDACTED] is CFPB's own token)

### Collections & Credit reporting

> *Product: Credit reporting · State: MO · Date: 2017-03-06*
>
> "Send credit bureau a letter informing them that I received a copy of my
> credit report. I asked that they send me copies that they have in their
> files as of this date that they used to verify the accuracy of the accounts
> below. My letter stated the following: Under the Fair Credit Reporting Act
> 15 U.S.C. § 1681i …"

---

### Loans

> *Product: Consumer Loan · State: CA · Date: 2016-08-07*
>
> "When my ex-wife failed to make payments on a leased car so I had the car
> picked up when we separated. [REDACTED] [REDACTED] turned us over to
> collection and in 2008, a judgement was entered … The original damage was
> {$9200.00}. This amount was for the lease buyout …"

---

### Cards

> *Product: Prepaid card · State: MD · Date: 2015-11-20*
>
> "When I bought my [REDACTED] phone, the app American Express Serve came with
> it. It auto opened an account, though I didn't think anything of it because
> I never used it. So there's no banking info or anything tied to it. Today I
> got an email saying that unless I add direct deposit to the account American
> Express will charge me a monthly fee …"

---

### Accounts

> *Product: Bank account or service · State: TN · Date: 2015-09-15*
>
> "I have had numerous unauthorized withdrawals from my checking and savings
> accounts with Suntrust Bank. [REDACTED] was an illegitimate PayPal account
> that was withdrawing directly from my savings and checking accounts. When I
> approached the bank to have these rescinded the person assisting me assisted
> me with getting the money back from one of the withdrawals …"

---

## 9. Cleaning Steps Applied (script: `backend/data/clean_banking_dataset.py`)

1. Read with `utf-8-sig` encoding to strip Excel / Kaggle BOM.
2. Normalise column names to canonical schema (see OUTPUT_COLUMNS in script).
3. Drop rows where `Consumer complaint narrative` is missing or blank.
4. Drop rows with narrative length < 200 characters.
5. Strip whitespace, collapse repeated spaces, normalise newlines to spaces.
   Replace CFPB anonymisation tokens (`XX`, `XXXX`, etc.) with `[REDACTED]`
   so TF-IDF does not treat redaction tokens as meaningful features.
6. Parse `Date received` to `YYYY-MM-DD`. Drop rows with unparseable dates
   (none dropped in this run — CFPB uses consistent `MM/DD/YYYY` format).
7. Map `Product` column to the 5 banking categories defined above.
   Unmapped products fall to `Other banking` (zero rows in this run).
8. Drop exact-duplicate narratives — keep first occurrence. (3,807 dropped.)
9. Drop rows with duplicate `Complaint ID` — keep first. (0 additional dropped.)
10. Undersample each class to max 3,000 rows using a fixed random seed (42)
    so results are reproducible.
11. Write `backend/data/banking_complaints.csv` with columns:
    `complaint, category, product_raw, date_month_year, state, received_via,
    issue, company, source`.

---

## 10. Known Issues / Limitations

| Issue | Notes |
|---|---|
| US-centric data | All complaints reference US banks, states, and currency. The live product uses Myanmar cities. This is a known intentional mismatch (see `docs/DECISIONS.md` Decision 17 / 25). |
| Class imbalance in raw data | Collections & Credit reporting dominated (43 %). Addressed by undersampling. |
| CFPB redaction tokens | `XXXX` masks account numbers, SSNs, names. Replaced with `[REDACTED]` to avoid treating them as vocabulary. |
| No official Low/Medium/High priority label | CFPB does not provide a priority column. Algorithm 2 uses distant supervision from `sentiment.py` — documented in `docs/ALGORITHMS.md`. |
| Narrative cap | Some narratives exceed 4,000 characters (max 12,344). These are kept as-is; the teacher explicitly requested long complaints. |
| "Other banking" category | Zero rows in this dataset — all products are covered by the mapping. Kept in code as a safety net. |

---

## 11. How to Rerun

```bash
# From the backend/ directory:
python -m data.clean_banking_dataset data/raw/consumer_complaints.csv
```

Or with an explicit path to a different raw file:

```bash
python -m data.clean_banking_dataset /path/to/your/consumer_complaints.csv
```

The script is idempotent — running it again overwrites `banking_complaints.csv`
with a deterministic result (fixed random seed 42).

---

## 12. What This File Trains

`banking_complaints.csv` is the ONLY file used by:

- `backend/app/ml/train_classifier.py` (Algorithm 1 — category)
- `backend/app/ml/train_priority.py` (Algorithm 2 — priority)
- `backend/app/dataset_seed.py` (auto-seed on first startup)
- `backend/data/load_dataset.py` (manual import)

**The chatbot (`backend/app/rag/`) does NOT train on this file.**
The chatbot reads `backend/data/knowledge_base/*.md` SOP documents only.
Complaint narratives describe problems; SOP documents describe solutions.
