"""
Shared feature engineering for Algorithm 2 (priority prediction) -
used by BOTH train_priority.py and priority_model.py so training and
inference can never silently drift out of sync with each other (a
classic bug: if the training script and the inference code build
features differently, the model quietly makes garbage predictions
with no error).

Features per complaint:
  - polarity, urgency, length, word_count, exclamation_count
    (from app/sentiment.py)
  - a small TF-IDF representation of the text itself (separate from
    Algorithm 1's TF-IDF vectorizer - kept small on purpose here,
    since priority is driven more by tone/urgency words than by the
    topic vocabulary that dominates category classification)
  - category, one-hot encoded against the fixed list in
    app/categories.py (+ an "unknown" bucket for when Algorithm 1
    hasn't run yet / wasn't supplied - see priority.py's docstring on
    why the two algorithms are independent, per the flowchart)
"""
from pathlib import Path

import numpy as np

from ..categories import CATEGORIES
from ..sentiment import analyze

CATEGORY_CHOICES = CATEGORIES + ["unknown"]


def _category_one_hot(category: str) -> list:
    cat = category if category in CATEGORY_CHOICES else "unknown"
    return [1.0 if cat == c else 0.0 for c in CATEGORY_CHOICES]


def numeric_features(text: str, category: str = None) -> list:
    """The non-TF-IDF part of the feature vector - sentiment/urgency
    signals plus one-hot category."""
    signals = analyze(text)
    base = [
        signals["polarity"],
        signals["urgency"],
        min(signals["length"], 1000) / 1000.0,       # normalized length
        min(signals["word_count"], 200) / 200.0,     # normalized word count
        min(signals["exclamation_count"], 5) / 5.0,  # normalized "shoutiness"
    ]
    return base + _category_one_hot(category)


def build_matrix(texts, categories, vectorizer, fit: bool):
    """Combines TF-IDF text features with numeric/category features
    into a single dense feature matrix. `vectorizer` must be an
    already-constructed (but not necessarily fitted) TfidfVectorizer;
    pass fit=True during training, fit=False at inference time."""
    if fit:
        text_features = vectorizer.fit_transform(texts).toarray()
    else:
        text_features = vectorizer.transform(texts).toarray()

    numeric = np.array([
        numeric_features(t, c) for t, c in zip(texts, categories)
    ])
    return np.hstack([text_features, numeric])
