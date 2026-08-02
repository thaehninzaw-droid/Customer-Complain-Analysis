from app.sentiment import analyze, score_polarity, score_urgency


def test_negative_words_score_below_zero():
    assert score_polarity("This is a terrible, awful experience") < 0


def test_positive_words_score_above_zero():
    assert score_polarity("Thanks, this was resolved quickly and the rep was friendly") > 0


def test_neutral_text_scores_near_zero():
    assert score_polarity("I have a question about my account") == 0


def test_negation_flips_polarity():
    # "not happy" should not score as positive just because "happy" is
    # a positive word - this is the exact bug class that was found and
    # fixed (contractions like "can't"/"isn't" tokenize as one word,
    # so a naive check for a literal "n't" token never matched anything).
    assert score_polarity("I am not happy with this service") < 0


def test_contraction_negation_is_detected():
    assert score_polarity("This isn't good at all") < 0


def test_urgency_terms_increase_score():
    calm = score_urgency("I have a small question, no rush at all")
    urgent = score_urgency("URGENT, I need this fixed immediately, this is unacceptable!")
    assert urgent > calm


def test_deescalation_phrase_suppresses_urgency():
    assert score_urgency("This is not urgent, whenever you get a chance is fine") < 0.2


def test_analyze_returns_expected_keys():
    result = analyze("My internet is down!")
    assert set(result.keys()) == {"polarity", "urgency", "length", "word_count", "exclamation_count"}
