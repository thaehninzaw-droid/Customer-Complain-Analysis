"""
Tests for app/analytics.py.

Decision 34 (banking pivot): sample documents updated to use banking
categories. The analytics module itself is category-agnostic (it just
counts whatever strings appear), so only the fixture data changes.
"""
from app.analytics import compute_analytics


def _doc(category="Cards", status="Pending", priority="Low", date="2026-07-01", received_via="Web Form"):
    return {
        "category": category, "status": status, "priority": priority,
        "date_month_year": date, "received_via": received_via,
    }


def test_empty_list_returns_zeroed_structure():
    result = compute_analytics([])
    assert result["total"] == 0
    assert result["by_category"] == {}
    assert len(result["monthly_volume"]) == 12
    assert result["trend"] is None or result["trend"]["this_month"] == 0


def test_counts_by_category_and_status_and_priority():
    docs = [
        _doc(category="Cards", status="Pending", priority="High"),
        _doc(category="Cards", status="Resolved", priority="Low"),
        _doc(category="Loans", status="Pending", priority="Medium"),
    ]
    result = compute_analytics(docs)
    assert result["total"] == 3
    assert result["by_category"] == {"Cards": 2, "Loans": 1}
    assert result["by_status"] == {"Pending": 2, "Resolved": 1}
    assert result["by_priority"] == {"High": 1, "Low": 1, "Medium": 1}


def test_monthly_volume_windows_off_the_data_not_todays_date():
    docs = [_doc(date="2015-06-01"), _doc(date="2015-06-15"), _doc(date="2015-04-22")]
    result = compute_analytics(docs)
    months = [m["month"] for m in result["monthly_volume"]]
    assert "2015-06" in months
    assert "2015-04" in months
    assert sum(m["count"] for m in result["monthly_volume"]) == 3
    counts_by_month = {m["month"]: m["count"] for m in result["monthly_volume"]}
    assert counts_by_month["2015-06"] == 2
    assert counts_by_month["2015-04"] == 1


def test_monthly_volume_is_chronologically_ordered_and_contiguous():
    docs = [_doc(date="2026-07-01"), _doc(date="2026-01-15")]
    result = compute_analytics(docs)
    months = [m["month"] for m in result["monthly_volume"]]
    assert months == sorted(months)
    assert months[0] == "2026-01"
    assert months[-1] == "2026-07"
    assert len(months) == 7


def test_monthly_volume_caps_at_24_months_for_a_long_history():
    docs = [_doc(date="2015-01-01"), _doc(date="2020-01-01")]
    result = compute_analytics(docs)
    assert len(result["monthly_volume"]) == 24
    months = [m["month"] for m in result["monthly_volume"]]
    assert months[-1] == "2020-01"
    assert "2015-01" not in months


def test_malformed_dates_are_ignored_not_crashed_on():
    docs = [_doc(date="not-a-date"), _doc(date=None), _doc(date="")]
    result = compute_analytics(docs)
    assert result["total"] == 3
    assert sum(m["count"] for m in result["monthly_volume"]) == 0


def test_all_five_banking_categories_counted_correctly():
    """Sanity check that analytics handles all 5 banking categories."""
    docs = [
        _doc(category="Cards"),
        _doc(category="Accounts"),
        _doc(category="Loans"),
        _doc(category="Collections & Credit reporting"),
        _doc(category="Other banking"),
    ]
    result = compute_analytics(docs)
    assert result["total"] == 5
    for cat in ["Cards", "Accounts", "Loans", "Collections & Credit reporting", "Other banking"]:
        assert result["by_category"][cat] == 1
