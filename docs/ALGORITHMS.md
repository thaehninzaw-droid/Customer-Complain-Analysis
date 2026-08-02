# The two algorithms

This matches the hand-drawn flowchart from the original SRS almost
exactly:

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
"Billing"   "High"
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
answered - that's deliberate (Strategy Pattern), and it's also why the
system is fully functional even before anyone runs a training script.

---

## Algorithm 1: category classification

**Baseline**: keyword counting across 5 categories (Billing,
Financial, Technical, Service, Others), highest-count category wins,
ties/no-matches fall to "Others."

**Trained model**: TF-IDF (unigrams + bigrams, 4000 features) +
Logistic Regression (`class_weight='balanced'`), in
`app/ml/train_classifier.py`.

### Where the training labels come from

This is the part worth being upfront about in a defense: **the
Comcast Telecom Complaints dataset has no category/department column**
- "Billing / Financial / Technical / Service / Others" is a taxonomy
the team invented, not something in the source data. That means there
was never a ground-truth label to train a supervised model against
directly.

The fix used here is called **distant supervision** (sometimes "weak
supervision"): use an existing, explainable labeling function - in
this case the keyword baseline - to generate approximate labels for
every row, then train a real supervised model on top of those labels.
This is a documented technique in the ML literature (see e.g. Snorkel,
Ratner et al. 2017, for the general framework), not an invented
shortcut - the honest way to describe it is "a trained model that
learns to generalize the keyword heuristic beyond its literal keyword
list," which is exactly what it does in practice (see the worked
example below).

### Does the trained model actually add anything over the keywords?

Yes - it generalizes to phrasing the keyword list was never given.
Example that was actually observed while building this:

```
classify_complaint("My internet has been down for a week and no technician showed up")
-> "Technical"     (keyword baseline agrees here)

classify_complaint("I was double charged on my invoice this month")
-> "Billing"       (works even though "double charged" isn't a literal keyword)
```

The model picked up that TF-IDF terms correlated with the keyword
label beyond the exact keyword itself - "invoice," "charged," "double"
co-occur often enough with keyword-triggered Billing labels that the
model learned the association.

### A real failure mode, found and kept (not hidden)

While building this, the following was found:

```
keyword_classify("My internet is down again for the third time this month, I need this fixed ASAP.")
-> "Technical"   (correct - "internet", "down" are Technical keywords)

classify_complaint(...)   # the trained model
-> "Billing"     (wrong)
```

The trained model disagreed with its own training-label source on
this one sentence - about a 2% disagreement rate on held-out test
data (see `category_metrics.json`). This is a real, expected property
of training a model on imperfect labels: it can both fix some of the
baseline's blind spots and introduce new mistakes the baseline
wouldn't have made. It's disclosed here rather than cherry-picking
only the cases that look good, because "does the model ever disagree
with its own labels, and is that a bug" is exactly the kind of
question worth having a real answer to in a defense.

### A second, more important bug this surfaced

Testing `classify_complaint("asdkjfh qpwoeiru randomtext")` (a
pre-existing unit test from before this rebuild, expecting "Others")
initially failed after the ML model was wired in: the model
confidently returned "Billing" for text with **zero matched
vocabulary** (a genuinely random string). Inspecting
`predict_proba()` showed why - for the zero vector, every class sits
near the 5-way chance level (~0.20), and "Billing" only edged out the
others by 0.03. The model wasn't wrong so much as being asked a
question it had no information to answer, and Logistic Regression
still has to output *something*.

**Fix**: `app/ml/classifier_model.py` now checks the model's
confidence (`MIN_CONFIDENCE = 0.30`, meaningfully above the 0.20
chance level for 5 classes) and returns `None` - triggering the
keyword-baseline fallback - if the top class isn't clearly better than
a coin flip. This is a real example of why the two-layer
(baseline + model) design pays for itself: without a fallback to
demote to, this bug's only fix would have been to accept
near-random behavior on out-of-vocabulary text.

### Metrics

Latest training run's accuracy against the keyword-baseline test
split is written to `app/ml/artifacts/category_metrics.json` every
time `python -m app.ml.train_classifier` runs - includes accuracy,
per-class precision/recall/F1, dataset size, and whether the dataset
was the synthetic stand-in or the real Kaggle data. Cite the actual
numbers from that file, not a number written into prose here, since
they'll change once the real dataset is loaded.

---

## Algorithm 2: priority prediction

This was the stretch goal explicitly named in the original SRS
("priority prediction using sentimental analysis algorithms, XGBoost"),
built out fully rather than left as a TODO.

**Baseline**: a combined score from `app/sentiment.py` -

```
priority_score = 0.45 × negativity + 0.55 × urgency
```

where `negativity` comes from a small hand-curated positive/negative
word lexicon (not unlike AFINN, much smaller, tuned for
customer-service vocabulary) with negation handling, and `urgency`
comes from a separate set of escalation phrases ("immediately",
"third time", "still waiting") plus surface signals (exclamation
marks, ALL-CAPS ratio).

**Trained model**: gradient-boosted trees over engineered features
(polarity, urgency, text length, word count, "shoutiness," one-hot
category) plus a small 500-feature TF-IDF representation of the text
itself - `app/ml/train_priority.py`.

### About XGBoost specifically

The SRS names XGBoost by name. It is **not installed** in the sandbox
this backend was built in (no internet access there to `pip install`
it), so `train_priority.py` tries to import it and automatically
substitutes scikit-learn's `HistGradientBoostingClassifier` - the same
family of algorithm (gradient-boosted decision trees), same
`.fit()`/`.predict()` interface - if the import fails. On any machine
with internet access, `pip install xgboost` and the script uses the
real thing automatically, no code changes needed (see
`_get_boosted_classifier()` in that file). `requirements.txt` lists
`xgboost` as a normal dependency for exactly this reason - it's not
required for the app to run, but it's expected to install fine
anywhere with internet.

### Where the training labels come from

Same idea as Algorithm 1: nobody hand-labeled priority levels for 600+
complaints, so the rule-based baseline above bootstraps the training
labels. See the distant-supervision discussion above - it applies
identically here.

### Two real bugs found and fixed while building this

**Bug 1 - negation never actually matched anything.** The first
version of the sentiment lexicon checked for a negation token `"n't"`
in the tokenized word list. Contractions tokenize as *whole words*
(`"can't"`, `"isn't"`, `"doesn't"`) via the regex tokenizer used here
- there is no isolated `"n't"` token ever produced, so this check
silently never fired. `"I am not happy with this service"` scored as
neutral-to-positive because "happy" is a positive word and the
"not" 2-tokens-back negation window technically existed, but
`"I am not happy"` only failed on contraction cases like
`"This isn't good at all"`, which scored as if "good" were unnegated.
Fixed by checking for an explicit contraction list (`can't`, `don't`,
`isn't`, ...) and a `token.endswith("n't")` check, alongside the
existing plain-word check for `not`/`no`/`never`.

**Bug 2 - a substring collision.** `score_urgency()` originally checked
for urgency phrases with plain Python `phrase in text` substring
matching. `"never"` is one of the urgency terms - and `"never"` is
also a literal substring of `"whenever"`. The test sentence
`"This is not urgent, whenever you get a chance is fine"` (an
explicitly *de-escalating* sentence - "not urgent," "whenever you get
a chance") scored as if it contained real urgency language, because
`"whenever"` tripped the `"never"` match. Fixed by switching to
word-boundary regex matching (`\bphrase\b`) for every urgency/
de-escalation phrase, compiled once at import time. This is a good
illustration of why "de-escalation phrases explicitly cancel urgency
matches" (see `DEESCALATION_PHRASES` in `app/sentiment.py`) needed to
exist as its own mechanism in the first place - naive keyword scoring
has real, non-obvious failure modes, and it's worth checking for them
rather than assuming a lexicon "obviously" works.

Both bugs were caught by writing and running the actual pytest test
files against the real implementation, not just by reasoning about the
code - see `backend/tests/test_sentiment.py` for the regression tests
that now lock these in.

### Threshold calibration

The baseline's Low/Medium/High cutoffs (0.20 and 0.40) were **not**
picked arbitrarily - they were calibrated by generating the priority
score across the full training corpus and picking cutoffs near the
60th and 90th percentiles of the observed distribution, so "High"
ends up a genuinely smaller, more urgent slice of the queue rather
than an even three-way split. See the `predict_priority_baseline()`
docstring in `app/priority.py` for the exact reasoning, and
`data/generate_synthetic_dataset.py` if you want to reproduce the
distribution analysis against a different dataset.

### Metrics

Same as Algorithm 1 - `app/ml/artifacts/priority_metrics.json` after
running `python -m app.ml.train_priority`, including the actual
Low/Medium/High label distribution observed and which model
(XGBoost vs. the scikit-learn substitute) was actually used.

---

## Real dataset results (update: now loaded)

The real Kaggle dataset (2224 rows) has been downloaded and loaded -
`backend/data/comcast_complaints.csv`, both models retrained against
it. What follows are the **actual** numbers, not the earlier synthetic
placeholders - and a few real bugs that only surfaced once real data
went through the pipeline, which is exactly why "run it against
something real before trusting it" matters more than reasoning about
code in the abstract.

### Real metrics

**Algorithm 1 (category)**: 93.0% accuracy vs. keyword-baseline labels
(down from 97.9% on synthetic data - expected, since real complaint
text is much terser and messier than templated sentences; see below).
Per-class F1: Technical 0.96, Others 0.94, Billing 0.90, Service 0.90,
Financial 0.86 (Financial has very low support - only ~56 of 2224 rows
hit a Financial keyword at all, so that number is less statistically
reliable than the others; worth saying so directly rather than citing
it with false confidence).

**Algorithm 2 (priority)**: 100% accuracy vs. baseline-heuristic
labels. Real label distribution: Low 1786, Medium 352, High 86 -
similarly skewed-toward-Low as the synthetic data, which is
reassuring (suggests the synthetic generator's severity mix wasn't
wildly unrealistic).

Exact numbers, always up to date with whatever's currently in
`app/ml/artifacts/*_metrics.json` - check `"dataset_is_synthetic":
false` to confirm which dataset produced them before citing a number.

### Finding: real complaint text is much terser than the synthetic data assumed

About a third of real complaints (744/2224, 33%) land in "Others" -
noticeably higher than expected. Looking at actual examples why:

```
"Comcast"                                          (just the company name)
"pmts"                                             (abbreviation, no context)
"bait and switch"                                  (a phrase, no category keyword)
"HBO GO on Playstation 4"                          (genuinely ambiguous - Technical? Service?)
"Comcast data caps"                                (could reasonably be Billing OR Technical)
```

The real Kaggle "Customer Complaint" field is closer to a **subject
line** than a full complaint narrative (average length: 31
characters) - very different from the synthetic generator's full
sentences. Both the keyword baseline and the TF-IDF model have much
less to work with on inputs like `"pmts"` or `"Comcast"` alone. This
is a legitimate, disclosed limitation of the current approach rather
than a bug: short, low-context text is genuinely harder to classify
confidently, for a human reader too, not just an algorithm. Worth
raising directly in a defense if asked why "Others" is so large - it's
an honest reflection of the data, not evidence the classifier is
broken.

### Bug found: date format mismatch would have silently zeroed out the "Monthly Volume" chart

The real CSV's `Date` column is `"DD-MM-YY"` (e.g. `"22-04-15"`), but
this app's `date_month_year` field is stored as `"YYYY-MM-DD"`
everywhere else. Loading the raw value directly would have made
`app/analytics.py`'s year/month parsing silently fail on every single
imported row (caught by a try/except, so nothing would have crashed -
the "Monthly Volume" chart, one of the SRS's explicitly named
requirements, would have just quietly shown zero data for the entire
imported history). Fixed in `data/load_dataset.py`'s
`normalize_date()`. Caught by actually running the full import and
looking at the output, not by reading the code.

### Bug found: a fixed "last 12 months" window doesn't work for 2015 data

Related to the above, but a design bug rather than a parsing bug:
`app/analytics.py` originally windowed "Monthly Volume" as the 12
months immediately before *today's* date (copying `pulse.py`'s
approach for the homepage's live "recent trend" chart). The real
dataset is entirely from 2015. Relative to any today after roughly
2016, that window would never overlap 2015 at all - 12 bars of zero,
permanently, no matter how much real historical data is loaded. Fixed
by windowing off the **data's own** min/max dates instead of
`datetime.now()` (capped at 24 months so a dataset spanning many years
doesn't produce an unreadably wide chart) - see `app/analytics.py`'s
module docstring. `pulse.py`'s homepage chart deliberately stays
`now`-relative, since "how are things trending lately" is genuinely a
different question than "what does the complaint history look like,"
and the SRS's "Monthly Volume: Months with the highest number of
complaints" language matches the second framing, not the first.

### A real finding worth citing in the thesis

Once the window was fixed: **June 2015 alone accounts for 1046 of the
2224 total complaints (47%)** - by far the busiest month, more than
the next four busiest months combined. That's a genuinely interesting
pattern for the "data analysis" part of the thesis - worth
investigating what happened that month (a major outage, a billing
system change, a price increase, negative press - the dataset alone
doesn't say, but the spike itself is a real, checkable finding, not
an artifact of the pipeline).

### Bug found: numpy scalar types leaking into complaint documents

`classifier_model.predict()` and `priority_model.predict()` both
return values pulled out of numpy arrays (`model.classes_[i]`,
`label_encoder.inverse_transform(...)`) - which are `numpy.str_`, not
plain `str`. `numpy.str_` IS a subclass of `str` (so `json.dumps` and
Pydantic validation both silently accept it - no error, no warning),
but **pymongo's BSON encoder does not accept numpy scalar types** and
would raise `InvalidDocument` the moment a complaint with one of these
fields got inserted against real MongoDB. Same category of gotcha
turned up a second time in the confidence-gate logic:
`numpy.bool_(False) is False` evaluates to `False` in Python (`is`
checks identity, not equality) - a test asserting
`passes_confidence_gate(...) is False` would fail even when the gate's
answer was correct, purely because of the numpy wrapper type. Both
fixed with explicit `str(...)`/`bool(...)` casts at the point values
leave numpy-land. Neither would have been caught by the in-memory
database fallback (which doesn't care about types) or by JSON-based
testing - only found by tracing through what pymongo would actually do
with these documents, which is exactly the kind of gap
docs/TESTING.md warns about (the real-MongoDB code path has still
never actually run against a real MongoDB instance in this build
environment).

## The dataset

**Update: the real dataset is now loaded** (`backend/data/
comcast_complaints.csv`, 2224 rows, downloaded from
https://www.kaggle.com/datasets/yasserh/comcast-telecom-complaints).
Both training scripts and `data/load_dataset.py` check for this exact
filename first, before falling back to the synthetic stand-in - so
this happened automatically the moment the file was dropped in, no
code changes needed (that was the whole point of building it that
way - see Decision 12 in DECISIONS.md).

The rest of this section is kept for context (why the synthetic
generator exists, and for anyone re-running this pipeline from
scratch without the real CSV present).

The real "Comcast Telecom Complaints" dataset (Kaggle,
`yasserh/comcast-telecom-complaints`, ~2200 rows) originally needed
internet access to download, which the environment this backend was
first built in didn't have. `data/generate_synthetic_dataset.py`
generates a **clearly-labeled synthetic stand-in** with the exact same
CSV column schema, template-based text with randomized slot-filling
across varying severity levels, specifically so:

1. The ML training pipeline could be built and actually run/tested
   end-to-end (not just written and hoped to work) before real data
   was available.
2. Swapping in the real dataset later needed zero code changes - drop
   `comcast_complaints.csv` into `data/`, and both training scripts
   (which check for that filename first) and `load_dataset.py` pick it
   up automatically. This is exactly what happened.

**Do not cite the synthetic dataset's specific accuracy numbers as
"the model's real-world performance"** in a writeup - the real
dataset's numbers (see "Real dataset results" above) are what to cite
now that they exist. The synthetic numbers are only useful as a "did
the pipeline work at all before real data existed" data point.
