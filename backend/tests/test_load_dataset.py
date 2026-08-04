from datetime import date, timedelta

from data.load_dataset import compute_demo_shift, normalize_date, normalize_status, normalize_time, parse_date


def test_parse_date_handles_kaggle_format():
    assert parse_date("22-04-15") == date(2015, 4, 22)


def test_parse_date_handles_already_normalized_format():
    assert parse_date("2026-07-01") == date(2026, 7, 1)


def test_parse_date_returns_none_for_garbage():
    assert parse_date("not-a-date") is None
    assert parse_date("") is None
    assert parse_date(None) is None


def test_normalize_date_converts_kaggle_format_to_app_format():
    assert normalize_date("22-04-15") == "2015-04-22"
    assert normalize_date("04-08-15") == "2015-08-04"


def test_normalize_date_falls_back_to_today_for_garbage():
    assert normalize_date("garbage") == date.today().strftime("%Y-%m-%d")


def test_normalize_time_converts_12_hour_to_24_hour():
    assert normalize_time("3:53:50 PM") == "15:53:50"
    assert normalize_time("9:55:47 AM") == "09:55:47"


def test_normalize_status_maps_kaggle_vocabulary():
    assert normalize_status("Solved") == "Resolved"
    assert normalize_status("Open") == "Pending"
    assert normalize_status("Closed") == "Closed"
    assert normalize_status("Pending") == "Pending"
    assert normalize_status("something unrecognized") == "Pending"


# ------------------------------------------------- demo-shift-dates ----

def test_compute_demo_shift_lands_the_latest_date_on_today():
    raw_dates = ["22-04-15", "04-08-15", "18-04-15"]  # latest is 04-08-15
    shift = compute_demo_shift(raw_dates)
    assert date(2015, 8, 4) + shift == date.today()


def test_compute_demo_shift_preserves_relative_spacing():
    raw_dates = ["22-04-15", "04-08-15"]
    shift = compute_demo_shift(raw_dates)
    original_gap = (date(2015, 8, 4) - date(2015, 4, 22)).days
    shifted_gap = ((date(2015, 8, 4) + shift) - (date(2015, 4, 22) + shift)).days
    assert original_gap == shifted_gap


def test_compute_demo_shift_is_zero_when_nothing_parses():
    assert compute_demo_shift(["garbage", "", None]) == timedelta(0)


def test_compute_demo_shift_ignores_unparseable_rows_but_uses_the_rest():
    raw_dates = ["22-04-15", "garbage", "04-08-15"]
    shift = compute_demo_shift(raw_dates)
    assert date(2015, 8, 4) + shift == date.today()
