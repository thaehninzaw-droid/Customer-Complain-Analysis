from app.priority import predict_priority_baseline, priority_score


def test_calm_low_stakes_text_is_low_priority():
    assert predict_priority_baseline("I have a small question about my invoice, not urgent.") == "Low"


def test_angry_escalated_text_is_high_priority():
    text = "URGENT!!! CANCEL MY ACCOUNT IMMEDIATELY, this is the worst service I have ever had, I am furious and will sue."
    assert predict_priority_baseline(text) == "High"


def test_priority_levels_are_ordered_consistently():
    calm_score = priority_score("I have a small question about my invoice, not urgent.")
    angry_score = priority_score("URGENT!!! I need this fixed immediately, I am furious!")
    assert angry_score > calm_score


def test_priority_score_stays_in_unit_range():
    for text in ["", "hello", "URGENT!!! " * 20]:
        score = priority_score(text)
        assert 0.0 <= score <= 1.0
