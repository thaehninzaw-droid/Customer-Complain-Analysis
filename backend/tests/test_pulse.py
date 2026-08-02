from datetime import datetime, timezone

from app.pulse import compute_pulse


def test_returns_12_values():
    result = compute_pulse([])
    assert len(result) == 12
    assert result == [0] * 12


def test_busiest_month_scales_to_100():
    ref = datetime(2026, 7, 15, tzinfo=timezone.utc)
    dates = ["2026-07-01"] * 4 + ["2026-06-01"] * 2
    result = compute_pulse(dates, reference=ref)
    assert result[-1] == 100          # current month (July) is busiest
    assert result[-2] == 50           # June is half as busy
    assert len(result) == 12


def test_ignores_malformed_dates():
    result = compute_pulse(["not-a-date", "", None])
    assert result == [0] * 12
