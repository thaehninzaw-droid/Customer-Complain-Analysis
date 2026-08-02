"""
Priority prediction - Algorithm 2 (the second algorithm from the
hand-drawn flowchart: "Incoming Raw Text" splits into Algorithm 1
[category] and Algorithm 2 [priority], both land in MongoDB, both show
up as sortable columns on the admin dashboard).

Same Strategy Pattern as app/classify.py: everything outside this file
only ever calls `predict_priority(text) -> "Low" | "Medium" | "High"`.
It has no idea whether that came from the rule-based baseline below or
the trained model in app/ml/priority_model.py - see predict_priority()
at the bottom, which prefers the trained model and falls back to the
baseline automatically (same zero-setup-fallback idea as app/db.py).

THE BASELINE (this file, always available, no training required):
Combines two signals from app/sentiment.py:
  - polarity : how negative the complaint sounds
  - urgency  : explicit time-pressure / escalation language
into one priority level. This is deliberately simple and fully
explainable - useful on day one, and also the source of the pseudo-
labels used to train the real model (see app/ml/train_priority.py and
docs/ALGORITHMS.md for why bootstrapping labels this way is a
legitimate, documented technique rather than a shortcut).
"""
from .sentiment import analyze

PRIORITY_LEVELS = ["Low", "Medium", "High"]


def priority_score(text: str) -> float:
    """Returns a single combined score in roughly [0, 1] - higher means
    more urgent/negative. urgency is weighted slightly higher than raw
    negativity, because a calmly-worded but repeatedly-escalated
    complaint ("this is the third technician who hasn't shown up")
    should still be treated as high priority."""
    signals = analyze(text)
    negativity = max(0.0, -signals["polarity"])  # only the negative half matters
    urgency = signals["urgency"]
    return max(0.0, min(1.0, 0.45 * negativity + 0.55 * urgency))


def predict_priority_baseline(text: str) -> str:
    """Rule-based fallback - no training required, always available.

    Thresholds below were calibrated empirically against the score
    distribution of the synthetic training corpus (see
    data/generate_synthetic_dataset.py + docs/ALGORITHMS.md), landing
    roughly on the 60th and 90th percentiles - i.e. "High" is
    deliberately a smaller, genuinely-urgent slice rather than half
    the queue, which is closer to how a real support team would want
    the label to behave. Re-run app/ml/train_priority.py's dataset
    analysis after swapping in the real Kaggle data to see whether
    these still make sense there."""
    score = priority_score(text)
    if score >= 0.40:
        return "High"
    if score >= 0.20:
        return "Medium"
    return "Low"


def predict_priority(text: str, category: str = None) -> str:
    """Public entry point. Tries the trained model first (see
    app/ml/priority_model.py); falls back to the rule-based baseline
    above if no trained artifact exists yet or scikit-learn isn't
    installed in this environment. `category` is accepted because the
    trained model uses it as a feature (some categories, e.g. Service,
    trend more urgent on average) - the baseline ignores it."""
    try:
        from .ml.priority_model import predict as ml_predict

        result = ml_predict(text, category)
        if result is not None:
            return result
    except Exception:
        # Any import/loading problem (artifacts missing, sklearn not
        # installed, etc.) - fall back rather than error the request.
        pass
    return predict_priority_baseline(text)
