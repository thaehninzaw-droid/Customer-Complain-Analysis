"""
Complaint classifier - Algorithm 1 from the hand-drawn flowchart.

Category names come from app/categories.py - the single source of
truth - not typed out again here. If that list changes, this file
doesn't need editing unless you're also changing the keyword mapping
for a category.

UPDATE (see docs/ALGORITHMS.md for the full writeup): this used to be
just the keyword baseline below. It's now a small dispatcher:

  classify_complaint(text) -> category
      Public entry point. Tries the trained TF-IDF + Logistic
      Regression model in app/ml/classifier_model.py first; if no
      trained artifact exists yet (or scikit-learn isn't installed),
      falls back to keyword_classify() below. Same zero-setup-fallback
      idea as app/db.py's Mongo/in-memory switch.

  keyword_classify(text) -> category
      The keyword-matching baseline. Used two ways:
      (1) as the safety-net fallback above, and (2) as the label
      source when the CSV has no 'category' column (distant supervision
      - see docs/ALGORITHMS.md). The banking_complaints.csv produced by
      clean_banking_dataset.py already has a 'category' column mapped
      from CFPB Product, so train_classifier.py uses those real labels
      directly and only falls back to this function if the column is
      absent.

Nothing outside this file needs to know which path is running - every
caller only ever uses classify_complaint(text) -> category. That
separation is the Strategy Pattern: "what gets decided" (a category)
is decoupled from "how it gets decided" (keywords vs a trained model).

Decision 34: keyword map updated from telecom to banking vocabulary.
"""
from .categories import CATEGORIES

CATEGORY_KEYWORDS = {
    "Cards": [
        "credit card", "debit card", "prepaid card", "card", "visa", "mastercard",
        "amex", "american express", "discover", "chargeback", "dispute charge",
        "unauthorized charge", "card number", "pin", "atm card",
    ],
    "Accounts": [
        "checking account", "savings account", "bank account", "direct deposit",
        "overdraft", "overdraft fee", "account balance", "wire transfer",
        "money transfer", "venmo", "zelle", "paypal", "withdrawal",
        "deposit", "account closed", "frozen account", "account hold",
    ],
    "Loans": [
        "mortgage", "loan", "student loan", "auto loan", "car loan",
        "personal loan", "payday loan", "refinance", "foreclosure",
        "monthly payment", "interest rate", "principal", "forbearance",
        "loan modification", "lender", "servicer", "title loan",
    ],
    "Collections & Credit reporting": [
        "credit report", "credit score", "collection", "debt", "collections",
        "collector", "credit bureau", "equifax", "experian", "transunion",
        "derogatory", "charge off", "charged off", "late payment",
        "debt collection", "credit inquiry", "dispute", "inaccurate",
    ],
}

DEFAULT_CATEGORY = "Other banking"

# Guardrail: catches the exact kind of drift we already found once
# (three different category lists across the codebase) the moment
# someone edits one file but forgets the other.
assert DEFAULT_CATEGORY in CATEGORIES, "DEFAULT_CATEGORY must be one of the categories in categories.py"
assert set(CATEGORY_KEYWORDS) <= set(CATEGORIES), "CATEGORY_KEYWORDS has a category not in categories.py"


def keyword_classify(text: str) -> str:
    """Returns the best-matching banking category for a complaint's text
    using plain keyword / phrase counting. Falls back to DEFAULT_CATEGORY
    ("Other banking") if nothing matches.

    Multi-word phrases (e.g. "credit card", "credit report") are checked
    with substring search on the lowercased text - same O(len(text)) cost
    as single-word checks, and far more precise than splitting on tokens.
    """
    text_lower = text.lower()
    scores = {
        category: sum(1 for kw in keywords if kw in text_lower)
        for category, keywords in CATEGORY_KEYWORDS.items()
    }
    best_category = max(scores, key=scores.get)
    if scores[best_category] == 0:
        return DEFAULT_CATEGORY
    return best_category


def classify_complaint(text: str) -> str:
    """Public entry point used everywhere else in the app. Prefers the
    trained model; falls back to the keyword baseline if no trained
    artifact is available yet (e.g. a fresh clone before anyone has
    run `python -m app.ml.train_classifier`)."""
    try:
        from .ml.classifier_model import predict as ml_predict

        result = ml_predict(text)
        if result is not None:
            return result
    except Exception:
        # Missing artifacts, scikit-learn not installed, or a corrupt
        # model file - never let a classifier problem break complaint
        # submission. Fall back to the always-available baseline.
        pass
    return keyword_classify(text)
