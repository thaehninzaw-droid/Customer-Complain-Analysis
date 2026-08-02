"""
Computes the 'pulse' series the homepage chart expects:
GET /issues/pulse returns an array of 12 numbers (0-100), one per
month, covering the last 12 months ending with the current month -
exactly what fetchPulseData() in script.js is already coded to expect.

Each value is that month's complaint count, scaled so the busiest
month in the window is 100 (min-max style scaling against 0).
"""
from datetime import datetime, timedelta, timezone

YANGON_TZ = timezone(timedelta(hours=6, minutes=30))


def _last_12_months(reference: datetime):
    months = []
    y, m = reference.year, reference.month
    for _ in range(12):
        months.append((y, m))
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    return list(reversed(months))


def compute_pulse(date_strings, reference: datetime = None) -> list:
    """date_strings: iterable of 'YYYY-MM-DD' strings (date_month_year
    field on each complaint). Missing/malformed dates are ignored."""
    reference = reference or datetime.now(YANGON_TZ)
    months = _last_12_months(reference)
    counts = {ym: 0 for ym in months}
    for s in date_strings:
        try:
            y, m = int(s[0:4]), int(s[5:7])
        except (ValueError, IndexError, TypeError):
            continue
        if (y, m) in counts:
            counts[(y, m)] += 1

    values = [counts[ym] for ym in months]
    peak = max(values) if values else 0
    if peak == 0:
        return [0] * 12
    return [round(v / peak * 100) for v in values]
