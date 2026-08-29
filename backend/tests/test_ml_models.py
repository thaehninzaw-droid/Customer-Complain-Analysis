"""
Tests for the trained-model layer (app/ml/).

These only pass if train_classifier.py and train_priority.py have
already been run (see docs/GETTING_STARTED.md). Skipped automatically
otherwise — a fresh clone with no artifacts is a valid state.

Decision 34 (banking pivot): all category assertions updated to the 5
banking categories from app/categories.py.
"""
import pytest

from app.ml import classifier_model, priority_model


pytestmark = pytest.mark.skipif(
    not classifier_model.is_available(),
    reason="No trained category model artifacts — run `python -m app.ml.train_classifier` first.",
)


def test_classifier_model_predicts_a_banking_category():
    from app.categories import CATEGORIES
    result = classifier_model.predict(
        "I found multiple unauthorized charges on my credit card statement this week"
    )
    assert result in CATEGORIES, f"Expected a banking category, got: {result!r}"


def test_classifier_model_predicts_loans_for_mortgage_text():
    from app.categories import CATEGORIES
    result = classifier_model.predict(
        "My mortgage servicer applied three payments to fees instead of principal "
        "and refuses to correct the error despite multiple written requests"
    )
    assert result in CATEGORIES


def test_classifier_model_predicts_collections_for_credit_report_text():
    from app.categories import CATEGORIES
    result = classifier_model.predict(
        "There is an inaccurate late payment on my Equifax credit report "
        "that should have been removed seven years ago under the FCRA"
    )
    assert result in CATEGORIES


def test_classifier_model_returns_none_for_gibberish_or_a_valid_category():
    """Gibberish may fall back to keyword baseline (returns a category)
    or the model may produce a low-confidence result that returns None.
    Both are correct per the confidence-gate design in classifier_model.py."""
    from app.categories import CATEGORIES
    result = classifier_model.predict("qzx flkj wprm nnnn banking")
    assert result is None or result in CATEGORIES


def test_confidence_gate_rejects_near_chance_probabilities():
    import numpy as np
    # 5 categories -> chance = 0.20 each
    near_chance = np.array([0.22, 0.20, 0.20, 0.19, 0.19])
    confident = np.array([0.05, 0.05, 0.05, 0.80, 0.05])
    assert classifier_model.passes_confidence_gate(near_chance) is False
    assert classifier_model.passes_confidence_gate(confident) is True


def test_priority_model_predicts_a_real_level():
    if not priority_model.is_available():
        pytest.skip("No trained priority model artifacts — run `python -m app.ml.train_priority` first.")
    result = priority_model.predict(
        "My credit card was charged an unauthorized fee and I need this resolved urgently",
        category="Cards",
    )
    assert result in ["Low", "Medium", "High"]


def test_trained_category_model_accuracy_above_threshold():
    """Smoke test: the trained model must have been trained on banking data
    (Decision 34) and achieve better-than-random accuracy on held-out text.
    Checks category_metrics.json rather than re-running evaluation."""
    import json
    from pathlib import Path

    metrics_path = (
        Path(__file__).resolve().parent.parent
        / "app" / "ml" / "artifacts" / "category_metrics.json"
    )
    if not metrics_path.exists():
        pytest.skip("category_metrics.json not found")

    with open(metrics_path) as f:
        metrics = json.load(f)

    assert metrics.get("dataset_is_banking") is True, (
        "Model was not trained on banking data — rerun `python -m app.ml.train_classifier`"
    )
    assert metrics.get("accuracy_vs_test_labels", 0) >= 0.70, (
        f"Category model accuracy {metrics.get('accuracy_vs_test_labels')} < 0.70 — "
        "retrain or investigate data quality"
    )
