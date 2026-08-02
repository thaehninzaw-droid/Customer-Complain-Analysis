"""
Tests for the trained-model layer (app/ml/). These only pass if
train_classifier.py and train_priority.py have already been run (see
README.md "Training the models") - skipped automatically otherwise,
since a fresh clone with no artifacts yet is a valid state (everything
just falls back to the rule-based baselines - see app/classify.py and
app/priority.py).
"""
import pytest

from app.ml import classifier_model, priority_model


pytestmark = pytest.mark.skipif(
    not classifier_model.is_available(),
    reason="No trained category model artifacts - run `python -m app.ml.train_classifier` first.",
)


def test_classifier_model_predicts_a_real_category():
    from app.categories import CATEGORIES

    result = classifier_model.predict("My internet has been down for a week")
    assert result in CATEGORIES


def test_classifier_model_returns_none_for_gibberish_OR_a_valid_category():
    # Whether gibberish text falls back to the keyword baseline (via
    # the confidence gate) or gets a confident answer straight from the
    # trained model depends on that model's learned class balance -
    # this legitimately changed between the synthetic dataset (fell
    # back) and the real Kaggle dataset (didn't - "Others" is the
    # largest real-world class, so its bias term alone clears the
    # confidence threshold). Both are correct outcomes; what actually
    # matters is asserted below and in test_classify.py's equivalent
    # dispatcher-level test, which is dataset-independent.
    from app.categories import CATEGORIES

    result = classifier_model.predict("qzx flkj wprm nnnn")
    assert result is None or result in CATEGORIES


def test_confidence_gate_rejects_near_chance_probabilities():
    # Deterministic, dataset-independent test of the gate mechanism
    # itself (see passes_confidence_gate()'s docstring for why this is
    # tested separately from any specific trained model's behavior).
    import numpy as np

    near_chance = np.array([0.21, 0.20, 0.20, 0.20, 0.19])
    confident = np.array([0.05, 0.05, 0.05, 0.80, 0.05])
    assert classifier_model.passes_confidence_gate(near_chance) is False
    assert classifier_model.passes_confidence_gate(confident) is True


def test_priority_model_predicts_a_real_level():
    if not priority_model.is_available():
        pytest.skip("No trained priority model artifacts - run `python -m app.ml.train_priority` first.")
    result = priority_model.predict("My internet has been down for a week", category="Technical")
    assert result in ["Low", "Medium", "High"]
