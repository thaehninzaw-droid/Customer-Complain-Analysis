"""
Loads the trained Algorithm 1 (category) model produced by
train_classifier.py and exposes a single predict() function.

Loaded lazily and cached at module level - the first call pays the
disk-read cost, every call after that is free. If the artifact files
don't exist (nobody has run train_classifier.py yet) or scikit-learn
isn't installed, predict() returns None so app/classify.py's
classify_complaint() falls back to the keyword baseline automatically.

CONFIDENCE GATE: predict() also returns None if the model's top
prediction isn't meaningfully more confident than chance (1 / number
of classes). This matters for text with ~zero matched TF-IDF
vocabulary (e.g. gibberish, or a language the vectorizer has never
seen) - the model still has to pick *something*, and without this
check it would confidently return whichever category happens to have
the largest bias term, which is a coin-flip artifact, not a real
prediction. Falling back to the keyword baseline in that situation is
strictly more honest. See docs/ALGORITHMS.md for the reasoning and
the specific example (a nonsense-text unit test) that surfaced this.
"""
from pathlib import Path

ARTIFACTS_DIR = Path(__file__).resolve().parent / "artifacts"

# Chance level for 5 categories is 0.2 - require the top class to clear
# this to be trusted. Calibrated loosely (not against a validation
# curve) - the goal is just "clearly better than a coin flip across 5
# options," not a precisely tuned number.
MIN_CONFIDENCE = 0.30

_vectorizer = None
_model = None
_load_attempted = False


def _load():
    global _vectorizer, _model, _load_attempted
    if _load_attempted:
        return
    _load_attempted = True
    vec_path = ARTIFACTS_DIR / "category_vectorizer.joblib"
    model_path = ARTIFACTS_DIR / "category_model.joblib"
    if not (vec_path.exists() and model_path.exists()):
        return
    import joblib

    _vectorizer = joblib.load(vec_path)
    _model = joblib.load(model_path)


def passes_confidence_gate(proba) -> bool:
    """The gate itself, pulled out as a pure function so it can be
    tested deterministically (see tests/test_ml_models.py) without
    depending on how any particular trained model happens to behave on
    any particular string - that behavior legitimately varies by
    training data (e.g. it changed between the synthetic dataset and
    the real one once "Other banking" became the largest class - see
    docs/ALGORITHMS.md), which makes it a poor thing to hang a test on
    directly."""
    return bool(proba.max() >= MIN_CONFIDENCE)


def predict(text: str):
    """Returns a predicted category string, or None if the trained
    model isn't available yet, or isn't confident enough (see
    MIN_CONFIDENCE above) - either way, the caller should fall back."""
    _load()
    if _model is None or _vectorizer is None:
        return None
    vec = _vectorizer.transform([text])
    proba = _model.predict_proba(vec)[0]
    if not passes_confidence_gate(proba):
        return None
    best_idx = proba.argmax()
    # str(...) matters here, not just style: _model.classes_ is a numpy
    # array, so indexing it returns numpy.str_, not a plain str. That's
    # a str subclass (json.dumps and Pydantic are fine with it) but
    # pymongo's BSON encoder rejects numpy scalar types outright against
    # real MongoDB - found by actually loading the full real dataset and
    # inspecting the resulting types, not by inspection alone.
    return str(_model.classes_[best_idx])


def is_available() -> bool:
    """Lets callers (e.g. an admin 'model status' endpoint) check
    whether a trained model is loaded without triggering a prediction."""
    _load()
    return _model is not None
