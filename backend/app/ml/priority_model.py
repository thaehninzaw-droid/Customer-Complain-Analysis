"""
Loads the trained Algorithm 2 (priority) model produced by
train_priority.py and exposes a single predict() function - same
lazy-singleton-cache pattern as app/ml/classifier_model.py.

If the artifact files don't exist yet or scikit-learn isn't
installed, predict() returns None so app/priority.py's
predict_priority() falls back to the rule-based baseline.
"""
from pathlib import Path

from .features import build_matrix

ARTIFACTS_DIR = Path(__file__).resolve().parent / "artifacts"

_vectorizer = None
_model = None
_label_encoder = None
_load_attempted = False


def _load():
    global _vectorizer, _model, _label_encoder, _load_attempted
    if _load_attempted:
        return
    _load_attempted = True
    vec_path = ARTIFACTS_DIR / "priority_vectorizer.joblib"
    model_path = ARTIFACTS_DIR / "priority_model.joblib"
    enc_path = ARTIFACTS_DIR / "priority_label_encoder.joblib"
    if not (vec_path.exists() and model_path.exists() and enc_path.exists()):
        return
    import joblib

    _vectorizer = joblib.load(vec_path)
    _model = joblib.load(model_path)
    _label_encoder = joblib.load(enc_path)


def predict(text: str, category: str = None):
    """Returns a predicted priority string ("Low"/"Medium"/"High"), or
    None if the trained model isn't available yet (caller should fall
    back). If `category` isn't supplied, it's computed via
    classify_complaint() to keep features identical to training time
    (train_priority.py always fills this in via the same function)."""
    _load()
    if _model is None or _vectorizer is None:
        return None

    if category is None:
        from ..classify import classify_complaint

        category = classify_complaint(text)

    x = build_matrix([text], [category], _vectorizer, fit=False)
    pred_encoded = _model.predict(x)[0]
    # str(...) - see classifier_model.py's predict() for why this isn't
    # just style: LabelEncoder.inverse_transform() also returns numpy
    # scalar types, which pymongo's BSON encoder rejects against real
    # MongoDB even though they're harmless for JSON/Pydantic.
    return str(_label_encoder.inverse_transform([pred_encoded])[0])


def is_available() -> bool:
    _load()
    return _model is not None
