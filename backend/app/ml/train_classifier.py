"""
Trains Algorithm 1 (category classification): TF-IDF features +
Logistic Regression, one-vs-rest across the 5 banking categories.

WHERE THE TRAINING LABELS COME FROM (read this before questioning the
methodology in a defense - it's a deliberate, documented choice, see
docs/ALGORITHMS.md for the full writeup):

Decision 34 (banking pivot): banking_complaints.csv already contains a
'category' column mapped directly from the CFPB Product field by
clean_banking_dataset.py. These are REAL, authoritative labels - not
distant supervision. The trainer uses them directly when present.

If the CSV has no 'category' column (e.g. a future custom dataset),
the trainer falls back to the original distant-supervision approach:
keyword_classify() generates approximate labels, the model trains on
those. This fallback preserves backward compatibility and is explicitly
documented so the defense can explain both paths.

Usage:
    python -m app.ml.train_classifier [path/to/complaints.csv]

    If no path is given, looks for (in order):
      1. data/banking_complaints.csv   (clean CFPB banking data - preferred)
      2. data/comcast_complaints.csv   (legacy telecom - not used after pivot)
      3. data/synthetic_complaints.csv (generated stand-in)
      4. data/sample_complaints.csv    (tiny 5-row smoke-test sample)

Writes to app/ml/artifacts/:
    category_vectorizer.joblib
    category_model.joblib
    category_metrics.json
"""
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent.parent))

from app.classify import keyword_classify  # noqa: E402

ARTIFACTS_DIR = Path(__file__).resolve().parent / "artifacts"
DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"


def _find_dataset(explicit_path: str = None) -> Path:
    if explicit_path:
        return Path(explicit_path)
    for name in (
        "banking_complaints.csv",
        "comcast_complaints.csv",
        "synthetic_complaints.csv",
        "sample_complaints.csv",
    ):
        candidate = DATA_DIR / name
        if candidate.exists():
            return candidate
    raise FileNotFoundError(
        "No dataset found. Run `python -m data.clean_banking_dataset` first, "
        "or pass a CSV path explicitly."
    )


def _load_texts_and_labels(csv_path: Path):
    """Load texts + labels from CSV.

    Prefers the 'category' column (official CFPB-mapped labels in
    banking_complaints.csv). Falls back to 'complaint' column name, then
    'Customer Complaint'. If no 'category' column exists, generates labels
    via keyword_classify() (distant supervision - documented fallback).
    """
    texts = []
    labels = []
    label_source = "official_cfpb_mapping"

    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    has_category_col = "category" in (rows[0].keys() if rows else [])
    if not has_category_col:
        label_source = "distant_supervision_keyword_classify"
        print(f"[train_classifier] No 'category' column found — "
              f"using keyword_classify() for distant supervision labels.")

    for row in rows:
        # Support both banking CSV ('complaint') and legacy CSV ('Customer Complaint')
        text = (row.get("complaint") or row.get("Customer Complaint") or "").strip()
        if not text:
            continue
        texts.append(text)
        if has_category_col:
            labels.append((row.get("category") or "").strip())
        else:
            labels.append(keyword_classify(text))

    return texts, labels, label_source


def train(csv_path: str = None):
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import train_test_split
    from sklearn.metrics import accuracy_score, classification_report
    import joblib

    dataset_path = _find_dataset(csv_path)
    texts, labels, label_source = _load_texts_and_labels(dataset_path)

    if len(texts) < 20:
        raise ValueError(
            f"Only found {len(texts)} rows in {dataset_path} - need at least ~20 to train on."
        )

    x_train, x_test, y_train, y_test = train_test_split(
        texts, labels, test_size=0.2, random_state=42, stratify=labels
    )

    vectorizer = TfidfVectorizer(
        max_features=4000,
        ngram_range=(1, 2),
        stop_words="english",
        min_df=1,
    )
    x_train_vec = vectorizer.fit_transform(x_train)
    x_test_vec = vectorizer.transform(x_test)

    model = LogisticRegression(max_iter=2000, class_weight="balanced")
    model.fit(x_train_vec, y_train)

    y_pred = model.predict(x_test_vec)
    accuracy = accuracy_score(y_test, y_pred)
    report = classification_report(y_test, y_pred, zero_division=0, output_dict=True)

    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(vectorizer, ARTIFACTS_DIR / "category_vectorizer.joblib")
    joblib.dump(model, ARTIFACTS_DIR / "category_model.joblib")

    is_banking = dataset_path.name == "banking_complaints.csv"
    metrics = {
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "dataset_path": str(dataset_path),
        "dataset_is_banking": is_banking,
        "n_rows_total": len(texts),
        "n_train": len(x_train),
        "n_test": len(x_test),
        "accuracy_vs_test_labels": round(accuracy, 4),
        "label_source": label_source,
        "classification_report": report,
        "model": (
            "TfidfVectorizer(max_features=4000, ngram_range=(1,2)) + "
            "LogisticRegression(class_weight='balanced')"
        ),
        "honesty_note": (
            "accuracy_vs_test_labels is measured against CFPB Product-derived labels "
            "(official ground truth) when label_source='official_cfpb_mapping', "
            "or against keyword baseline pseudo-labels when label_source="
            "'distant_supervision_keyword_classify'. See docs/ALGORITHMS.md."
        ) if is_banking else (
            "Trained on non-banking dataset. Labels are keyword-baseline pseudo-labels."
        ),
    }
    with open(ARTIFACTS_DIR / "category_metrics.json", "w") as f:
        json.dump(metrics, f, indent=2)

    print(f"Dataset:  {dataset_path} ({'BANKING' if is_banking else 'other'}, {len(texts)} rows)")
    print(f"Labels:   {label_source}")
    print(f"Train/test split: {len(x_train)}/{len(x_test)}")
    print(f"Accuracy vs {'CFPB-mapped' if is_banking else 'keyword-baseline'} labels: {accuracy:.3f}")
    print(f"Saved model + vectorizer to {ARTIFACTS_DIR}")
    return metrics


if __name__ == "__main__":
    train(sys.argv[1] if len(sys.argv) > 1 else None)
