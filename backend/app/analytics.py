"""
Aggregate analytics for the admin dashboard (SRS Module 3.1.C: monthly
volume, category distribution, trend analysis). Pure functions - take
a list of complaint docs (already fetched from the DB, same
"fetch-everything-then-work-in-Python" style used everywhere else in
this small codebase, see pulse.py) and return plain dicts the frontend
charts can consume directly with no extra reshaping.

MONTHLY VOLUME WINDOW - deliberately NOT "the last 12 months relative
to today," unlike pulse.py's /issues/pulse (the public homepage's
"recent trend" chart, which correctly IS meant to be relative to now).
This surfaced as a real bug while loading the actual Kaggle dataset:
that data is entirely from 2015. A "last 12 months relative to today"
window (today being 2026+) would show 12 bars of zero forever, even
though the SRS explicitly wants "Months with the highest number of
complaints" - i.e. analysis of the data's own history, not a live
rolling window. Fixed by windowing off the data's own min/max dates
instead of `datetime.now()`. Capped at 24 months (most recent end of
the range) so a dataset spanning many years doesn't produce an
unreadably wide chart - 24 was picked as "two full years of monthly
bars," comfortably more than the ~12 months actually present in either
the real or synthetic dataset used while building this.
"""
from collections import Counter
from datetime import date


MAX_MONTHS = 24


def _parse_year_month(date_month_year):
    try:
        return int(date_month_year[0:4]), int(date_month_year[5:7])
    except (ValueError, IndexError, TypeError):
        return None


def _month_range(start_ym, end_ym, cap=MAX_MONTHS):
    """Every (year, month) tuple from start_ym to end_ym inclusive,
    chronological order. If that span exceeds `cap` months, keeps only
    the most recent `cap` - the chart favors recency over completeness
    once a dataset spans a long enough history."""
    months = []
    y, m = start_ym
    end_y, end_m = end_ym
    while (y, m) <= (end_y, end_m):
        months.append((y, m))
        m += 1
        if m > 12:
            m = 1
            y += 1
    return months[-cap:] if len(months) > cap else months


def compute_analytics(docs: list) -> dict:
    by_category = Counter(d.get("category", "Other banking") for d in docs)
    by_status = Counter(d.get("status", "Pending") for d in docs)
    by_priority = Counter(d.get("priority", "Low") for d in docs)
    by_received_via = Counter(d.get("received_via", "Web Form") for d in docs)

    year_months = [ym for ym in (_parse_year_month(d.get("date_month_year")) for d in docs) if ym]

    if year_months:
        months = _month_range(min(year_months), max(year_months))
    else:
        # No usable dates anywhere (empty collection, or every date
        # failed to parse) - fall back to a 12-month window ending this
        # month, purely so the chart still renders a sensible axis
        # instead of an empty one.
        today = date.today()
        end_ym = (today.year, today.month)
        start_y, start_m = today.year, today.month - 11
        while start_m <= 0:
            start_m += 12
            start_y -= 1
        months = _month_range((start_y, start_m), end_ym)

    month_counts = {ym: 0 for ym in months}
    for ym in year_months:
        if ym in month_counts:
            month_counts[ym] += 1

    monthly_volume = [
        {"month": f"{y:04d}-{m:02d}", "count": month_counts[(y, m)]}
        for (y, m) in months
    ]

    busiest_month = max(monthly_volume, key=lambda x: x["count"]) if any(m["count"] for m in monthly_volume) else None

    # Trend: most recent month in the window vs. the one before it -
    # "Trend Analysis: Volume trends across different time periods"
    # from the SRS. Kept intentionally simple (month-over-month).
    trend = None
    if len(monthly_volume) >= 2:
        this_month = monthly_volume[-1]["count"]
        last_month = monthly_volume[-2]["count"]
        delta = this_month - last_month
        pct = round((delta / last_month) * 100, 1) if last_month else None
        trend = {"this_month": this_month, "last_month": last_month, "delta": delta, "delta_pct": pct}

    return {
        "total": len(docs),
        "by_category": dict(by_category),
        "by_status": dict(by_status),
        "by_priority": dict(by_priority),
        "by_received_via": dict(by_received_via),
        "monthly_volume": monthly_volume,
        "busiest_month": busiest_month,
        "trend": trend,
    }
