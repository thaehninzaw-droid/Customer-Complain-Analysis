"""
Integration tests for the FastAPI layer.

Decision 34 (banking pivot):
  - Category assertions updated from Billing/Technical/etc. to banking categories.
  - test_manual_category_overrides_auto_classify removed: the customer-facing
    POST /complaints no longer accepts a category from the client (server always
    classifies). Admin POST /admin/complaints still accepts an override.
  - test_chatbot_recommend updated: expects a banking category.
  - test_repeat_same_day_forces_high_priority added: covers the new business rule.
  - test_categories_endpoint updated: expects banking categories.
"""
import pytest
from fastapi.testclient import TestClient

from app.admin_seed import ensure_admin_seeded
from app.main import app

client = TestClient(app)


@pytest.fixture(scope="module", autouse=True)
def _ensure_admin_exists():
    ensure_admin_seeded()


def _signup(email="jane@example.com", username="Jane Doe", password="Passw0rd!"):
    return client.post("/auth/signup", json={"username": username, "email": email, "password": password})


def _admin_login():
    import os
    email = os.getenv("ADMIN_EMAIL", "admin@loopline.io")
    password = os.getenv("ADMIN_PASSWORD", "ChangeMe123!")
    resp = client.post("/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, f"admin login failed: {resp.text}"
    return resp.json()


def _auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


# ------------------------------------------------------------- basics ----

def test_health_check():
    resp = client.get("/")
    assert resp.status_code == 200


def test_signup_and_login_return_token():
    resp = _signup()
    assert resp.status_code == 200
    body = resp.json()
    assert "token" in body
    assert body["user"]["email"] == "jane@example.com"
    assert body["user"]["role"] == "customer"

    resp = client.post("/auth/login", json={"email": "jane@example.com", "password": "Passw0rd!"})
    assert resp.status_code == 200
    assert "token" in resp.json()


def test_login_wrong_password_fails():
    _signup(email="bob@example.com")
    resp = client.post("/auth/login", json={"email": "bob@example.com", "password": "WrongPass1!"})
    assert resp.status_code == 401


def test_signup_weak_password_rejected():
    resp = _signup(email="weak@example.com", password="weak")
    assert resp.status_code == 400


def test_signup_duplicate_email_rejected():
    _signup(email="dupe@example.com")
    resp = _signup(email="dupe@example.com")
    assert resp.status_code == 400


# --------------------------------------------------------- complaints ----

def test_complaint_requires_auth():
    resp = client.post("/complaints", json={"complaint": "no token attached"})
    assert resp.status_code == 401


def test_complaint_rejects_bad_token():
    resp = client.post(
        "/complaints",
        json={"complaint": "bad token"},
        headers=_auth_headers("garbage-token"),
    )
    assert resp.status_code == 401


def test_create_complaint_classifies_to_banking_category():
    """POST /complaints must return a banking category from Algorithm 1."""
    from app.categories import CATEGORIES
    auth = _signup(email="banking_user@example.com").json()
    resp = client.post(
        "/complaints",
        json={"complaint": "I found an unauthorized charge on my credit card statement last week and the bank has not responded."},
        headers=_auth_headers(auth["token"]),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["category"] in CATEGORIES
    assert body["priority"] in ["Low", "Medium", "High"]
    assert body["status"] == "Pending"
    assert body["received_via"] == "Web Form"
    assert body["user_id"] == auth["user"]["user_id"]


def test_customer_form_does_not_accept_category_field():
    """The client must NOT be able to dictate the category — it is always
    classified server-side (Decision 34). Sending 'category' in the body
    must be silently ignored (or the endpoint ignores it per the schema)."""
    from app.categories import CATEGORIES
    auth = _signup(email="no_cat_override@example.com").json()
    resp = client.post(
        "/complaints",
        json={
            "complaint": "I found an unauthorized charge on my credit card and need a refund urgently.",
            "category": "Billing",   # old telecom category — must be ignored
        },
        headers=_auth_headers(auth["token"]),
    )
    assert resp.status_code == 200
    body = resp.json()
    # category must be a banking category, not the stale telecom value sent by client
    assert body["category"] in CATEGORIES
    assert body["category"] != "Billing"


def test_create_and_list_own_complaint():
    auth = _signup(email="complainer2@example.com").json()
    resp = client.post(
        "/complaints",
        json={"complaint": "My mortgage payment was applied incorrectly three times this year and no one has fixed it."},
        headers=_auth_headers(auth["token"]),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["priority"] in ["Low", "Medium", "High"]
    assert body["status"] == "Pending"
    assert body["user_id"] == auth["user"]["user_id"]

    resp = client.get("/complaints", headers=_auth_headers(auth["token"]))
    assert resp.status_code == 200
    assert len(resp.json()) >= 1
    assert all(c["user_id"] == auth["user"]["user_id"] for c in resp.json())


def test_priority_reflects_urgency_not_just_a_constant():
    """Exercises Algorithm 2 at the HTTP layer with banking-domain text."""
    auth = _signup(email="urgency_banking@example.com").json()
    calm = client.post(
        "/complaints",
        json={"complaint": "I have a small question about my savings account balance, no rush at all."},
        headers=_auth_headers(auth["token"]),
    ).json()
    urgent = client.post(
        "/complaints",
        json={
            "complaint": (
                "URGENT!!!! My account has been frozen without notice. "
                "I cannot pay my rent. This is the third time this month!!!! "
                "I will escalate to the CFPB immediately if this is not resolved TODAY."
            )
        },
        headers=_auth_headers(auth["token"]),
    ).json()
    assert calm["priority"] == "Low"
    assert urgent["priority"] == "High"


def test_repeat_same_day_complaint_forces_high_priority():
    """Business rule Decision 34: same user, same day, similar text -> High."""
    auth = _signup(email="repeat_user@example.com").json()
    headers = _auth_headers(auth["token"])
    complaint_text = (
        "My debit card was charged twice at the grocery store yesterday "
        "and I need a refund for the duplicate charge immediately."
    )
    # First submission — priority is whatever the model decides
    first = client.post("/complaints", json={"complaint": complaint_text}, headers=headers).json()
    # Second identical submission same day — must be High regardless
    second = client.post("/complaints", json={"complaint": complaint_text}, headers=headers).json()
    assert second["priority"] == "High", (
        f"Expected High for same-day repeat complaint, got {second['priority']!r}"
    )


def test_idor_is_fixed_users_cannot_see_each_others_complaints():
    """IDOR regression guard: user A must never see user B's complaints."""
    auth_a = _signup(email="usera_banking@example.com").json()
    auth_b = _signup(email="userb_banking@example.com").json()

    client.post("/complaints", json={"complaint": "A's private banking complaint about overdraft fees"}, headers=_auth_headers(auth_a["token"]))
    client.post("/complaints", json={"complaint": "B's private banking complaint about credit report error"}, headers=_auth_headers(auth_b["token"]))

    texts_a = [c["complaint"] for c in client.get("/complaints", headers=_auth_headers(auth_a["token"])).json()]
    assert not any("B's private" in t for t in texts_a)

    texts_b = [c["complaint"] for c in client.get("/complaints", headers=_auth_headers(auth_b["token"])).json()]
    assert not any("A's private" in t for t in texts_b)


def test_complaint_too_short_rejected_server_side():
    auth = _signup(email="tooshort_banking@example.com").json()
    resp = client.post(
        "/complaints",
        json={"complaint": "too short"},
        headers=_auth_headers(auth["token"]),
    )
    assert resp.status_code == 400
    assert "20" in resp.json()["detail"]


def test_complaint_too_long_rejected_server_side():
    auth = _signup(email="toolong_banking@example.com").json()
    resp = client.post(
        "/complaints",
        json={"complaint": "x" * 1001},
        headers=_auth_headers(auth["token"]),
    )
    assert resp.status_code == 400


def test_complaint_with_unknown_city_rejected_server_side():
    auth = _signup(email="badcity_banking@example.com").json()
    resp = client.post(
        "/complaints",
        json={
            "complaint": "My credit card was charged an unauthorized fee three times this month.",
            "city": "Atlantis",
        },
        headers=_auth_headers(auth["token"]),
    )
    assert resp.status_code == 400
    assert "Atlantis" in resp.json()["detail"]


def test_complaint_with_known_city_accepted_case_insensitive():
    auth = _signup(email="goodcity_banking@example.com").json()
    resp = client.post(
        "/complaints",
        json={
            "complaint": "My credit card was charged an unauthorized fee three times this month.",
            "city": "yangon",
        },
        headers=_auth_headers(auth["token"]),
    )
    assert resp.status_code == 200
    assert resp.json()["city"] == "yangon"


def test_complaint_with_no_city_still_works():
    auth = _signup(email="nocity_banking@example.com").json()
    resp = client.post(
        "/complaints",
        json={"complaint": "My mortgage servicer has not applied my payment correctly for two months."},
        headers=_auth_headers(auth["token"]),
    )
    assert resp.status_code == 200


# ------------------------------------------------------- public/misc ----

def test_dashboard_stats():
    resp = client.get("/dashboard-stats")
    assert resp.status_code == 200
    body = resp.json()
    assert "by_category" in body
    assert "by_status" in body
    assert "by_priority" in body


def test_pulse_endpoint_returns_12_numbers():
    resp = client.get("/issues/pulse")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 12
    assert all(0 <= v <= 100 for v in body)


def test_categories_endpoint_returns_banking_categories():
    resp = client.get("/categories")
    assert resp.status_code == 200
    categories = resp.json()
    assert set(categories) == {
        "Cards",
        "Accounts",
        "Loans",
        "Collections & Credit reporting",
        "Other banking",
    }
    assert len(categories) == 5


def test_cities_endpoint():
    resp = client.get("/cities")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 63
    assert all({"city", "state", "zip"} == set(entry.keys()) for entry in body)
    assert any(entry["city"] == "Yangon" for entry in body)


def test_chatbot_recommend_returns_banking_category():
    from app.categories import CATEGORIES
    resp = client.post(
        "/chatbot/recommend",
        json={"complaint_text": "I have an unauthorized charge on my credit card and I want a refund"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["category"] in CATEGORIES
    assert "recommendation" in body


# ------------------------------------------------------------- admin ----

def test_admin_complaints_requires_auth():
    resp = client.get("/admin/complaints")
    assert resp.status_code == 401


def test_admin_complaints_rejects_customer_token():
    auth = _signup(email="notadmin_banking@example.com").json()
    resp = client.get("/admin/complaints", headers=_auth_headers(auth["token"]))
    assert resp.status_code == 403


def test_admin_complaints_returns_paginated_shape_for_real_admin():
    admin = _admin_login()
    resp = client.get("/admin/complaints", headers=_auth_headers(admin["token"]))
    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) == {"items", "total", "page", "page_size"}
    assert isinstance(body["items"], list)


def test_admin_manual_entry_and_inline_edit():
    admin = _admin_login()
    headers = _auth_headers(admin["token"])

    created = client.post(
        "/admin/complaints",
        json={"complaint": "Customer called about a suspected fraudulent charge on their debit card", "received_via": "Phone Call"},
        headers=headers,
    )
    assert created.status_code == 200
    body = created.json()
    assert body["user_id"] == 0
    assert body["received_via"] == "Phone Call"
    ticket_no = body["ticket_no"]

    patched = client.patch(
        f"/admin/complaints/{ticket_no}", json={"status": "Resolved"}, headers=headers,
    )
    assert patched.status_code == 200
    assert patched.json()["status"] == "Resolved"

    bad = client.patch(
        f"/admin/complaints/{ticket_no}", json={"status": "NotARealStatus"}, headers=headers,
    )
    assert bad.status_code == 400

    missing = client.patch("/admin/complaints/999999", json={"status": "Resolved"}, headers=headers)
    assert missing.status_code == 404


def test_admin_manual_entry_also_enforces_server_side_validation():
    admin = _admin_login()
    headers = _auth_headers(admin["token"])
    resp = client.post(
        "/admin/complaints",
        json={"complaint": "short", "city": "Nowhereville"},
        headers=headers,
    )
    assert resp.status_code == 400


def test_admin_analytics_shape():
    admin = _admin_login()
    resp = client.get("/admin/analytics", headers=_auth_headers(admin["token"]))
    assert resp.status_code == 200
    body = resp.json()
    for key in ["total", "by_category", "by_status", "by_priority", "monthly_volume"]:
        assert key in body
    assert len(body["monthly_volume"]) >= 1


def test_admin_ml_status_shape():
    admin = _admin_login()
    resp = client.get("/admin/ml-status", headers=_auth_headers(admin["token"]))
    assert resp.status_code == 200
    body = resp.json()
    assert "category_model" in body and "priority_model" in body
    assert "available" in body["category_model"]


def test_admin_chatbot_ask_falls_back_gracefully_without_gemini_key():
    admin = _admin_login()
    resp = client.post(
        "/admin/chatbot/ask",
        json={"question": "How should I handle a repeat complaint about unauthorized credit card charges?"},
        headers=_auth_headers(admin["token"]),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "answer" in body
    assert isinstance(body["used_rag"], bool)


def test_admin_chatbot_ask_rejects_unknown_ticket():
    admin = _admin_login()
    resp = client.post(
        "/admin/chatbot/ask",
        json={"question": "What's going on with this ticket?", "ticket_no": 999999},
        headers=_auth_headers(admin["token"]),
    )
    assert resp.status_code == 404
