# The two algorithms

This matches the hand-drawn flowchart from the original SRS:

```
[ Incoming Raw Text ]
        │
   ┌────┴─────┐
   ▼          ▼
Algorithm 1  Algorithm 2
Category     Priority
Classify     Predict
   │          │
   ▼          ▼
Category:   Priority:
"Cards"     "High"
   └────┬─────┘
        ▼
 [ Saved into MongoDB ]
        ▼
 [ Admin Dashboard View ]
(sort by Category AND Priority)
```

Both algorithms follow the same two-layer design:

1. **A rule-based baseline** that needs no training data and is always
   available (`keyword_classify()` in `app/classify.py`,
   `predict_priority_baseline()` in `app/priority.py`).
2. **A trained ML model** that a public dispatcher function
   (`classify_complaint()`, `predict_priority()`) prefers when
   available, falling back to the baseline otherwise.

Nothing outside `classify.py`/`priority.py` needs to know which layer
answered — that is the Strategy Pattern, and it is also why the system
is fully functional even before anyone runs a training script.

---

## Algorithm 1: category classification

**Five banking categories** (Decision 34, August 2026):

| Category | What it covers |
|---|---|
| Cards | Credit cards, debit cards, prepaid cards, chargebacks, unauthorized charges |
| Accounts | Checking/savings accounts, overdrafts, wire transfers, frozen accounts |
| Loans | Mortgages, student loans, auto loans, payday loans, loan modifications, foreclosure |
| Collections & Credit reporting | Debt collection calls, FCRA disputes, credit bureau errors, identity theft |
| Other banking | Hidden fees, account opening/closure, virtual currency, escalations |

**Baseline**: keyword/phrase counting across the 5 categories (see
`CATEGORY_KEYWORDS` in `app/classify.py`). The keyword map uses
multi-word phrases (e.g. "credit card", "credit report", "loan
modification") — checked with substring search on lowercased text —
because single-word matching was too imprecise for banking vocabulary
where the same word ("credit") appears in several different categories.
Highest-score category wins; ties/no-matches fall to "Other banking".

**Trained model**: TF-IDF (unigrams + bigrams, 4 000 features) +
Logistic Regression (`class_weight='balanced'`), in
`app/ml/train_classifier.py`.

### Where the training labels come from

**Decision 34 update**: the banking dataset (`banking_complaints.csv`)
already contains a `category` column produced by
`clean_banking_dataset.py` from the CFPB `Product` field (see the full
mapping in `backend/data/EDA.md` and `docs/DECISIONS.md` Decision 34).
These are **real, authoritative labels** — not distant supervision. The
classifier is trained directly on them.

The distant-supervision fallback (using `keyword_classify()` to
generate pseudo-labels) is kept in the code for any CSV that arrives
without a `category` column. It is clearly labelled as a fallback in
`train_classifier.py` and in `category_metrics.json`
(`"label_source": "official_cfpb_mapping"` vs.
`"distant_supervision_keyword_classify"`).

### Metrics

**Banking dataset (12 000 rows, 3 000 per class, CFPB-mapped labels)**:

- Accuracy on held-out test split: **86.5 %**
- Label source: `"official_cfpb_mapping"` (real CFPB Product → category mapping)
- Training set: 9 600 rows | Test set: 2 400 rows

Full per-class precision/recall/F1 in
`app/ml/artifacts/category_metrics.json`. Check
`"dataset_is_banking": true` before citing a number to confirm the
artifact reflects the current banking dataset, not any legacy run.

### Confidence gate

`app/ml/classifier_model.py` checks the model's top-class probability
against `MIN_CONFIDENCE = 0.30` (meaningfully above the 0.20 chance
level for 5 classes). If the top class does not clear the gate, the
dispatcher returns `None` and the keyword baseline answers instead.
This prevents the model from confidently mis-classifying zero-
vocabulary input (e.g. random strings or very short text) — a real
failure mode observed during development.

### Does the trained model add anything over the keywords?

Yes — it generalizes to phrasing the keyword list was never given.
Examples observed with the banking model:

```
classify_complaint("I disputed a double-billing on my statement last month")
-> "Cards"   (keyword baseline: "billing" doesn't appear in Cards keywords,
              but the model learned the co-occurrence of "statement" + "disputed")

classify_complaint("The servicer applied my payment to accrued interest instead of principal")
-> "Loans"   (no exact keyword match, but learned from "servicer" + "payment" context)
```

---

## Algorithm 2: priority prediction

**Three levels**: Low / Medium / High.

**Baseline** (`predict_priority_baseline()` in `app/priority.py`):

```
priority_score = 0.45 × negativity + 0.55 × urgency
```

- `negativity` — hand-curated positive/negative word lexicon (tuned
  for banking customer-service vocabulary) with negation handling
  (checks a 2-token window before each scored word; handles
  contractions like "can't", "isn't" via `token.endswith("n't")`)
- `urgency` — escalation phrases (e.g. "immediately", "third time",
  "still waiting", "foreclosure", "unauthorized charge", "identity
  theft") plus surface signals (exclamation marks, ALL-CAPS ratio,
  repeated question marks), with de-escalation phrases ("not urgent",
  "no rush") explicitly subtracting from the score

**Thresholds** (calibrated near the 60th and 90th percentiles of the
score distribution so "High" is a genuinely small, urgent slice):

```
score >= 0.40  →  High
score >= 0.20  →  Medium
score <  0.20  →  Low
```

These are **calibrated cutoffs, not a published formula**. They are
documented here and in the `predict_priority_baseline()` docstring so
there is no confusion during a defense. Do not cite them as a standard
without that qualifier.

**Trained model**: gradient-boosted trees (`XGBClassifier` if
`xgboost` is installed, `HistGradientBoostingClassifier` otherwise —
same family, same interface; see `_get_boosted_classifier()` in
`train_priority.py`) over:
- Sentiment features: polarity, urgency, text length, word count,
  exclamation count (all from `app/sentiment.py`)
- One-hot category (from Algorithm 1)
- 500-feature TF-IDF representation of the text

### Where the training labels come from

The CFPB dataset has no official Low/Medium/High priority column.
Labels are generated by **distant supervision** from
`predict_priority_baseline()` — the same rule-based heuristic above
bootstraps the training labels, then the tree learns to generalize its
patterns. The accuracy figure in `priority_metrics.json` measures the
trained tree against those heuristic pseudo-labels (it should be near
1.0, because the tree is approximating its own teacher). This is
documented honestly under `"honesty_note"` in `priority_metrics.json`.

### Same-user same-day repeat rule (Decision 34)

A business rule layered **on top of** the model in `main.py`:

```python
if _is_repeat_same_day(user_id, new_text, new_date, existing):
    priority = "High"   # overrides whatever the model returned
```

`_is_repeat_same_day()` returns True when:
1. The same `user_id` already filed at least one complaint with the
   same `date_month_year`, AND
2. The new text is an exact match (after normalising whitespace) OR has
   Jaccard word-set overlap ≥ 0.70 with any of those prior complaints

Jaccard is computed on lowercased whitespace-split word sets — O(n)
in text length, interpretable, and sufficient for detecting
resubmissions. The rule runs server-side and cannot be bypassed via
the frontend.

### Banking-specific urgency terms added (Decision 34)

`app/sentiment.py` was extended with banking-domain urgency signals:

| Term | Weight |
|---|---|
| `overdraft` | 3 |
| `foreclosure` | 3 |
| `unauthorized charge` | 3 |
| `identity theft` | 3 |
| `fraud` | 3 |
| `garnished` / `garnishment` | 3 |
| `account frozen` | 3 |
| `collections call` | 2 |
| `three times` / `twice` | 3 / 2 |
| `account closed` | 2 |

These were absent from the original telecom lexicon and are necessary
for the baseline to correctly classify banking escalations as High
without purely depending on the trained model.

### About XGBoost specifically

The SRS names XGBoost by name. `train_priority.py` tries to import it
and automatically substitutes `HistGradientBoostingClassifier` if the
import fails (no code change needed). `requirements.txt` lists `xgboost`
as a normal dependency so `pip install -r requirements.txt` on any
internet-connected machine installs it automatically.

### Metrics

**Banking dataset (12 000 rows)**:

- Label distribution: Low ≈ 3 500 | Medium ≈ 3 000 | High ≈ 5 500
  (the banking dataset's long narratives contain more urgency signals
  than the short Comcast subject-lines did)
- Accuracy vs. baseline pseudo-labels: **99.8 %**
  (the tree approximates its teacher almost perfectly — expected)
- Model used: XGBClassifier (if xgboost installed) or
  HistGradientBoostingClassifier

Full metrics in `app/ml/artifacts/priority_metrics.json`. Check
`"dataset_is_banking": true` before citing.

---

## Two real bugs found during development — kept here for the defense

### Bug 1 — negation never actually matched contractions

The first version checked for a negation token `"n't"` in the
tokenized word list. Contractions tokenize as whole words (`"can't"`,
`"isn't"`) — there is no isolated `"n't"` token produced by the regex
tokenizer. `"This isn't good at all"` scored as if "good" were
unnegated. Fixed by checking `token.endswith("n't")` and an explicit
contraction list alongside the plain `"not"`/`"no"`/`"never"` check.

### Bug 2 — substring collision in urgency matching

`score_urgency()` originally used plain `phrase in text` substring
matching. `"never"` is an urgency term; `"never"` is also a substring
of `"whenever"`. The de-escalating sentence "This is not urgent,
whenever you get a chance is fine" scored as urgently as an actual
complaint because `"whenever"` tripped the `"never"` match. Fixed by
switching to word-boundary regex (`\bphrase\b`) compiled once at import
time. This is also why `DEESCALATION_PHRASES` exists — naive keyword
scoring has real failure modes that only appear on specific real inputs.

Both bugs were caught by running `pytest tests/test_sentiment.py` — not
by reading the code. The regression tests now lock them in.

---

## The dataset

**Current dataset**: CFPB Consumer Complaints (Kaggle:
`sebastienverpile/consumercomplaintsdata`).

- Raw: 903 983 rows, 18 columns, stored untouched at
  `backend/data/raw/consumer_complaints.csv`
- Clean: 12 000 rows, 3 000 per banking category, at
  `backend/data/banking_complaints.csv`
- Cleaning pipeline: `backend/data/clean_banking_dataset.py`
  (reproducible, deterministic seed 42)
- Full EDA: `backend/data/EDA.md`

The original synthetic generator (`data/generate_synthetic_dataset.py`)
and the legacy Comcast CSV loader (`data/load_dataset.py`) are
preserved for backward compatibility. Do **not** cite synthetic dataset
accuracy numbers as real-world performance.
