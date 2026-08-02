from app.classify import classify_complaint


def test_billing_keyword():
    assert classify_complaint("I was overcharged on my bill") == "Billing"


def test_financial_keyword():
    assert classify_complaint("I never got my refund back") == "Financial"


def test_technical_keyword():
    assert classify_complaint("My internet keeps disconnecting") == "Technical"


def test_service_keyword():
    assert classify_complaint("The representative was very rude") == "Service"


def test_unmatched_falls_back_to_others():
    assert classify_complaint("asdkjfh qpwoeiru randomtext") == "Others"
