import pytest

from app.validation import ComplaintValidationError, validate_city, validate_complaint_text


def test_valid_length_passes():
    validate_complaint_text("My bill was charged twice this month and I need a refund please.")


def test_too_short_rejected():
    with pytest.raises(ComplaintValidationError):
        validate_complaint_text("too short")


def test_too_long_rejected():
    with pytest.raises(ComplaintValidationError):
        validate_complaint_text("x" * 1001)


def test_exact_boundary_lengths_pass():
    validate_complaint_text("x" * 20)
    validate_complaint_text("x" * 1000)


def test_whitespace_is_stripped_before_length_check():
    # 18 real characters padded with whitespace to look longer than it is
    with pytest.raises(ComplaintValidationError):
        validate_complaint_text("   " + "x" * 18 + "   ")


def test_empty_or_none_rejected():
    with pytest.raises(ComplaintValidationError):
        validate_complaint_text("")
    with pytest.raises(ComplaintValidationError):
        validate_complaint_text(None)


def test_known_city_passes():
    validate_city("Yangon")


def test_known_city_case_insensitive():
    validate_city("yangon")
    validate_city("YANGON")


def test_unknown_city_rejected():
    with pytest.raises(ComplaintValidationError):
        validate_city("Atlantis")


def test_blank_or_none_city_allowed():
    # city is optional - no city sent should never be an error
    validate_city(None)
    validate_city("")
    validate_city("   ")
