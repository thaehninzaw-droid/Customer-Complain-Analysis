"""
Tests for Algorithm 1 — complaint category classification.

Decision 34 (banking pivot): categories changed from
Billing / Financial / Technical / Service / Others
to
Cards / Accounts / Loans / Collections & Credit reporting / Other banking

Tests use banking-domain complaint text that clearly belongs to one
category according to the keyword map in app/classify.py.
"""
from app.classify import classify_complaint, keyword_classify
from app.categories import CATEGORIES


# ---------------------------------------------------------------- keyword baseline ----

def test_cards_keyword():
    assert keyword_classify("I found an unauthorized charge on my credit card statement") == "Cards"


def test_accounts_keyword():
    assert keyword_classify("My checking account has been frozen and I cannot make withdrawals") == "Accounts"


def test_loans_keyword():
    assert keyword_classify("My mortgage payment was applied incorrectly to interest") == "Loans"


def test_collections_keyword():
    assert keyword_classify("There is an inaccurate late payment on my credit report from Equifax") == "Collections & Credit reporting"


def test_unmatched_falls_back_to_other_banking():
    assert keyword_classify("asdkjfh qpwoeiru randomtext") == "Other banking"


# ---------------------------------------------------------------- dispatcher ----

def test_dispatcher_returns_a_valid_category():
    """classify_complaint() (the public dispatcher) must always return
    one of the 5 official banking categories, whether it goes through
    the trained model or the keyword baseline fallback."""
    result = classify_complaint("My debit card was charged twice at the same merchant")
    assert result in CATEGORIES


def test_dispatcher_handles_empty_string_without_crashing():
    result = classify_complaint("")
    assert result in CATEGORIES


def test_dispatcher_handles_gibberish_without_crashing():
    result = classify_complaint("zzzzz pppppp random gibberish 12345")
    assert result in CATEGORIES


def test_all_categories_are_reachable_via_keywords():
    """Every banking category must be reachable via the keyword map
    so the fallback always produces meaningful output."""
    probes = {
        "Cards": "unauthorized charge on my visa credit card",
        "Accounts": "overdraft fee on my checking account",
        "Loans": "my mortgage servicer applied the payment incorrectly",
        "Collections & Credit reporting": "debt collector calls me before 8 AM every day",
        "Other banking": "I was charged a hidden fee I was not told about",
    }
    for expected_cat, text in probes.items():
        result = keyword_classify(text)
        assert result == expected_cat, f"Expected '{expected_cat}' for: {text!r}, got: {result!r}"
