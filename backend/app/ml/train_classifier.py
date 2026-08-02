"""
Trains Algorithm 1 (category classification): TF-IDF features +
Logistic Regression, one-vs-rest across the 5 categories.

WHERE THE TRAINING LABELS COME FROM (read this before questioning the
methodology in a defense - it's a deliberate, documented choice, see
docs/ALGORITHMS.md for the full writeup):

The Comcast Telecom Complaints dataset has NO category/department
column - the team invented the 5 categories. That means there is no
ground truth to train a supervised model against directly. The fix
used here is called "distant supervision" (a.k.a. weak supervision):
use an existing, explainable labeling function - app/classify.py's
keyword_classify() - to generate approximate labels for every row,
then train a real supervised model on top of those labels. This is a
real, citable technique from the weak-supervision literature (see
e.g. Snorkel, Ratner et al. 2017), not a shortcut - it lets the
trained model learn to generalize BEYOND the fixed keyword list (e.g.
recognizing a billing complaint that never uses the literal word
"bill"), while still being fully explainable about where its
starting point came from.

Usage:
    python -m app.ml.train_classifier [path/to/complaints.csv]

    If no path is given, looks for (in order):
      1. data/comcast_complaints.csv   (the real Kaggle dataset, once
         someone with internet access has downloaded it)
      2. data/synthetic_complaints.csv (generated stand-in - see
         data/generate_synthetic_dataset.py)
      3. data/sample_complaints.csv    (tiny 5-row smoke-test sample)

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
    for name in ("comcast_complaints.csv", "synthetic_complaints.csv", "sample_complaints.csv"):
        candidate = DATA_DIR / name
        if candidate.exists():
            return candidate
    raise FileNotFoundError(
        "No dataset found. Run `python -m data.generate_synthetic_dataset` "
        "first, or pass a CSV path explicitly."
    )


def _load_texts(csv_path: Path):
    texts = []
    # utf-8-sig strips a leading BOM if present (the real Kaggle CSV has
    # one - Excel-exported CSVs commonly do) and behaves like plain utf-8
    # otherwise, so this is safe for both the synthetic and real datasets.
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            text = (row.get("Customer Complaint") or "").strip()
            if text:
                texts.append(text)
    return texts


def train(csv_path: str = None):
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import train_test_split
    from sklearn.metrics import accuracy_score, classification_report
    import joblib

    dataset_path = _find_dataset(csv_path)
    texts = _load_texts(dataset_path)
    if len(texts) < 20:
        raise ValueError(f"Only found {len(texts)} rows in {dataset_path} - need at least ~20 to train on.")

    labels = [keyword_classify(t) for t in texts]

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

    metrics = {
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "dataset_path": str(dataset_path),
        "dataset_is_synthetic": dataset_path.name != "comcast_complaints.csv",
        "n_rows_total": len(texts),
        "n_train": len(x_train),
        "n_test": len(x_test),
        "accuracy_vs_keyword_labels": round(accuracy, 4),
        "classification_report": report,
        "label_source": "distant supervision from app.classify.keyword_classify "
                         "(see module docstring / docs/ALGORITHMS.md)",
        "model": "TfidfVectorizer(max_features=4000, ngram_range=(1,2)) + "
                 "LogisticRegression(class_weight='balanced')",
    }
    with open(ARTIFACTS_DIR / "category_metrics.json", "w") as f:
        json.dump(metrics, f, indent=2)

    print(f"Dataset: {dataset_path} ({'SYNTHETIC' if metrics['dataset_is_synthetic'] else 'real'}, {len(texts)} rows)")
    print(f"Train/test split: {len(x_train)}/{len(x_test)}")
    print(f"Accuracy vs keyword-baseline labels: {accuracy:.3f}")
    print(f"Saved model + vectorizer to {ARTIFACTS_DIR}")
    return metrics


if __name__ == "__main__":
    train(sys.argv[1] if len(sys.argv) > 1 else None)
