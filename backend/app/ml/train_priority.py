"""
Trains Algorithm 2 (priority prediction): sentiment/urgency features +
a small TF-IDF representation, fed into a boosted-tree classifier
(XGBoost if available, scikit-learn's HistGradientBoostingClassifier
otherwise - see the "About XGBoost" note below).

WHERE THE TRAINING LABELS COME FROM - same idea as train_classifier.py,
see docs/ALGORITHMS.md for the full writeup:
Nobody hand-labeled 600+ complaints with a "true" priority level, so
this uses app/priority.py's rule-based baseline (polarity + urgency
score -> Low/Medium/High) to generate pseudo-labels, then trains a
real classifier on top. The trained model's value-add over the
baseline: it learns smoother, nonlinear combinations of the input
signals (and picks up on phrasing patterns via TF-IDF) instead of the
baseline's fixed 0.55/0.25 score thresholds - and it's a drop-in
replacement, since app/priority.py's predict_priority() already
prefers this trained model and only falls back to the baseline if
these artifacts don't exist.

ABOUT XGBOOST: the project's stretch goal explicitly asks for
XGBoost. It is NOT installed in this development sandbox (no internet
access to pip install it here), so this script tries to import it
and, if unavailable, automatically substitutes scikit-learn's
HistGradientBoostingClassifier - also a gradient-boosted-trees model,
same family of algorithm, same .fit()/.predict() shape. On any machine
with internet access, `pip install xgboost` and this script will use
the real thing automatically - no code changes needed. See
DECISIONS.md for this trade-off written up as a proper ADR entry.

Usage:
    python -m app.ml.train_priority [path/to/complaints.csv]

Writes to app/ml/artifacts/:
    priority_vectorizer.joblib
    priority_model.joblib
    priority_metrics.json
"""
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent.parent))

from app.classify import classify_complaint  # noqa: E402
from app.priority import predict_priority_baseline  # noqa: E402
from app.ml.features import build_matrix  # noqa: E402

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
    # See train_classifier.py's _load_texts for why utf-8-sig, not utf-8.
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            text = (row.get("Customer Complaint") or "").strip()
            if text:
                texts.append(text)
    return texts


def _get_boosted_classifier():
    """Prefers real XGBoost; falls back to scikit-learn's own
    gradient-boosted-trees implementation if xgboost isn't installed.
    Returns (model, model_name_string)."""
    try:
        from xgboost import XGBClassifier

        model = XGBClassifier(
            n_estimators=200, max_depth=4, learning_rate=0.1,
            eval_metric="mlogloss", random_state=42,
        )
        return model, "XGBClassifier(n_estimators=200, max_depth=4)"
    except ImportError:
        from sklearn.ensemble import HistGradientBoostingClassifier

        model = HistGradientBoostingClassifier(max_depth=4, random_state=42)
        return model, "HistGradientBoostingClassifier(max_depth=4) [xgboost not installed - see module docstring]"


def train(csv_path: str = None):
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.model_selection import train_test_split
    from sklearn.metrics import accuracy_score, classification_report
    from sklearn.preprocessing import LabelEncoder
    import joblib

    dataset_path = _find_dataset(csv_path)
    texts = _load_texts(dataset_path)
    if len(texts) < 20:
        raise ValueError(f"Only found {len(texts)} rows in {dataset_path} - need at least ~20 to train on.")

    categories = [classify_complaint(t) for t in texts]
    labels = [predict_priority_baseline(t) for t in texts]

    idx = list(range(len(texts)))
    idx_train, idx_test = train_test_split(idx, test_size=0.2, random_state=42, stratify=labels)

    def _subset(lst, indices):
        return [lst[i] for i in indices]

    texts_train, texts_test = _subset(texts, idx_train), _subset(texts, idx_test)
    cats_train, cats_test = _subset(categories, idx_train), _subset(categories, idx_test)
    y_train, y_test = _subset(labels, idx_train), _subset(labels, idx_test)

    vectorizer = TfidfVectorizer(max_features=500, ngram_range=(1, 2), stop_words="english")
    x_train = build_matrix(texts_train, cats_train, vectorizer, fit=True)
    x_test = build_matrix(texts_test, cats_test, vectorizer, fit=False)

    label_encoder = LabelEncoder()
    y_train_enc = label_encoder.fit_transform(y_train)
    y_test_enc = label_encoder.transform(y_test)

    model, model_name = _get_boosted_classifier()
    model.fit(x_train, y_train_enc)

    y_pred_enc = model.predict(x_test)
    accuracy = accuracy_score(y_test_enc, y_pred_enc)
    report = classification_report(
        y_test_enc, y_pred_enc, target_names=label_encoder.classes_, zero_division=0, output_dict=True
    )

    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(vectorizer, ARTIFACTS_DIR / "priority_vectorizer.joblib")
    joblib.dump(model, ARTIFACTS_DIR / "priority_model.joblib")
    joblib.dump(label_encoder, ARTIFACTS_DIR / "priority_label_encoder.joblib")

    metrics = {
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "dataset_path": str(dataset_path),
        "dataset_is_synthetic": dataset_path.name != "comcast_complaints.csv",
        "n_rows_total": len(texts),
        "n_train": len(texts_train),
        "n_test": len(texts_test),
        "accuracy_vs_baseline_labels": round(float(accuracy), 4),
        "classification_report": report,
        "label_distribution": {lvl: labels.count(lvl) for lvl in ["Low", "Medium", "High"]},
        "label_source": "distant supervision from app.priority.predict_priority_baseline "
                         "(see module docstring / docs/ALGORITHMS.md)",
        "model": model_name,
        "features": "sentiment/urgency signals (app.sentiment) + one-hot category + "
                     "500-feature TF-IDF (see app/ml/features.py)",
    }
    with open(ARTIFACTS_DIR / "priority_metrics.json", "w") as f:
        json.dump(metrics, f, indent=2)

    print(f"Dataset: {dataset_path} ({'SYNTHETIC' if metrics['dataset_is_synthetic'] else 'real'}, {len(texts)} rows)")
    print(f"Label distribution: {metrics['label_distribution']}")
    print(f"Model: {model_name}")
    print(f"Train/test split: {len(texts_train)}/{len(texts_test)}")
    print(f"Accuracy vs baseline-heuristic labels: {accuracy:.3f}")
    print(f"Saved model + vectorizer + label encoder to {ARTIFACTS_DIR}")
    return metrics


if __name__ == "__main__":
    train(sys.argv[1] if len(sys.argv) > 1 else None)
