"""
Tests for Algorithm 2 — priority prediction.

Covers:
  - predict_priority_baseline() rule-based heuristic
  - priority_score() raw score in [0, 1]
  - Same-user same-day repeat override (Decision 34)
"""
from app.priority import predict_priority_baseline, priority_score


# ---------------------------------------------------------------- baseline heuristic ----

def test_calm_low_stakes_banking_text_is_low_priority():
    text = "I have a small question about my account balance, no rush."
    assert predict_priority_baseline(text) == "Low"


def test_angry_escalated_banking_text_is_high_priority():
    text = (
        "URGENT!!! My account was FROZEN without any notice and I cannot pay "
        "my mortgage. This is the third time this month. I demand this be "
        "resolved IMMEDIATELY or I will file a CFPB complaint and take legal action."
    )
    assert predict_priority_baseline(text) == "High"


def test_banking_fraud_language_triggers_high_priority():
    text = (
        "There are multiple unauthorized transactions on my account. "
        "I believe my card number was stolen. Please escalate immediately."
    )
    assert predict_priority_baseline(text) == "High"


def test_foreclosure_mention_is_high_priority():
    text = (
        "The bank has initiated foreclosure proceedings even though I submitted "
        "a complete loan modification application three weeks ago. "
        "I need a supervisor to review this urgently."
    )
    assert predict_priority_baseline(text) == "High"


def test_priority_levels_are_ordered_consistently():
    calm_score = priority_score("I have a small question about my savings account balance.")
    angry_score = priority_score(
        "URGENT!!!! My account is frozen, I cannot access my funds, "
        "this has happened 3 times and I am losing money every day!!!!"
    )
    assert angry_score > calm_score


def test_priority_score_stays_in_unit_range():
    for text in ["", "hello", "URGENT!!! " * 20, "fraud " * 50]:
        score = priority_score(text)
        assert 0.0 <= score <= 1.0, f"Score out of range for: {text[:40]!r}"


def test_exclamation_marks_raise_urgency():
    base = "My credit card was declined"
    with_exclamations = "My credit card was declined!!!! This is unacceptable!!!!"
    assert priority_score(with_exclamations) > priority_score(base)


def test_repeated_complaint_language_is_high():
    text = (
        "I have called three times about this unauthorized charge and no one "
        "has resolved it. This is the third time I am reporting the same issue."
    )
    assert predict_priority_baseline(text) == "High"


# ---------------------------------------------------------------- same-day repeat override ----

def test_repeat_same_day_helper_triggers_on_similar_text():
    """The _is_repeat_same_day helper must return True when a user files
    a substantially similar complaint on the same date."""
    from app.main import _is_repeat_same_day

    existing = [
        {
            "user_id": 42,
            "date_month_year": "2026-08-01",
            "complaint": "My debit card was charged twice at the same merchant yesterday",
        }
    ]
    new_text = "My debit card was charged twice at the same merchant yesterday"
    assert _is_repeat_same_day(42, new_text, "2026-08-01", existing) is True


def test_repeat_same_day_helper_ignores_different_user():
    from app.main import _is_repeat_same_day

    existing = [
        {
            "user_id": 99,           # different user
            "date_month_year": "2026-08-01",
            "complaint": "My debit card was charged twice at the same merchant",
        }
    ]
    assert _is_repeat_same_day(42, "My debit card was charged twice at the same merchant", "2026-08-01", existing) is False


def test_repeat_same_day_helper_ignores_different_date():
    from app.main import _is_repeat_same_day

    existing = [
        {
            "user_id": 42,
            "date_month_year": "2026-07-31",  # yesterday
            "complaint": "My debit card was charged twice at the same merchant",
        }
    ]
    assert _is_repeat_same_day(42, "My debit card was charged twice at the same merchant", "2026-08-01", existing) is False


def test_repeat_same_day_helper_triggers_on_high_jaccard():
    from app.main import _is_repeat_same_day

    existing = [
        {
            "user_id": 7,
            "date_month_year": "2026-08-05",
            "complaint": "I cannot access my online banking account because it is locked and frozen",
        }
    ]
    # Word sets: original has {i,cannot,access,my,online,banking,account,because,it,is,locked,and,frozen} = 13 words
    # Similar has  {i,cannot,access,my,online,banking,account,because,it,is,locked,and,frozen,out} = 14 words
    # overlap = 13, union = 14, jaccard = 13/14 = 0.929 -> well above 0.70
    similar = "I cannot access my online banking account because it is locked and frozen out"
    assert _is_repeat_same_day(7, similar, "2026-08-05", existing) is True


def test_repeat_same_day_helper_ignores_low_jaccard():
    from app.main import _is_repeat_same_day

    existing = [
        {
            "user_id": 7,
            "date_month_year": "2026-08-05",
            "complaint": "I cannot access my online banking account because it is locked",
        }
    ]
    # Completely different complaint on the same day — must NOT trigger
    different = "My mortgage payment was applied to fees instead of principal"
    assert _is_repeat_same_day(7, different, "2026-08-05", existing) is False
