from app.analytics import compute_analytics


def _doc(category="Billing", status="Pending", priority="Low", date="2026-07-01", received_via="Web Form"):
    return {
        "category": category, "status": status, "priority": priority,
        "date_month_year": date, "received_via": received_via,
    }


def test_empty_list_returns_zeroed_structure():
    result = compute_analytics([])
    assert result["total"] == 0
    assert result["by_category"] == {}
    assert len(result["monthly_volume"]) == 12  # no dates at all -> the 12-month fallback window
    assert result["trend"] is None or result["trend"]["this_month"] == 0


def test_counts_by_category_and_status_and_priority():
    docs = [
        _doc(category="Billing", status="Pending", priority="High"),
        _doc(category="Billing", status="Resolved", priority="Low"),
        _doc(category="Technical", status="Pending", priority="Medium"),
    ]
    result = compute_analytics(docs)
    assert result["total"] == 3
    assert result["by_category"] == {"Billing": 2, "Technical": 1}
    assert result["by_status"] == {"Pending": 2, "Resolved": 1}
    assert result["by_priority"] == {"High": 1, "Low": 1, "Medium": 1}


def test_monthly_volume_windows_off_the_data_not_todays_date():
    # This is the exact bug found while loading the real (2015) Kaggle
    # dataset: a fixed "last 12 months relative to today" window would
    # show this as 12 empty bars forever. The window must come from the
    # data's own date range instead - see analytics.py's module docstring.
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
    assert len(months) == 7  # every month in between is present, even the zero ones


def test_monthly_volume_caps_at_24_months_for_a_long_history():
    docs = [_doc(date="2015-01-01"), _doc(date="2020-01-01")]
    result = compute_analytics(docs)
    assert len(result["monthly_volume"]) == 24
    # capped range keeps the MOST RECENT end, so the earliest complaint
    # (2015) falls outside the window and the latest (2020) doesn't
    months = [m["month"] for m in result["monthly_volume"]]
    assert months[-1] == "2020-01"
    assert "2015-01" not in months


def test_malformed_dates_are_ignored_not_crashed_on():
    docs = [_doc(date="not-a-date"), _doc(date=None), _doc(date="")]
    result = compute_analytics(docs)
    assert result["total"] == 3
    assert sum(m["count"] for m in result["monthly_volume"]) == 0
