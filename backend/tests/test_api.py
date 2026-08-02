import pytest
from fastapi.testclient import TestClient

from app.admin_seed import ensure_admin_seeded
from app.main import app

client = TestClient(app)


@pytest.fixture(scope="module", autouse=True)
def _ensure_admin_exists():
    # Deliberately NOT relying on app.main's @app.on_event("startup")
    # hook firing via TestClient - whether a plain (non-context-manager)
    # TestClient(app) triggers startup events is genuinely version-
    # dependent across Starlette releases. Seeding directly here is
    # explicit and version-independent.
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
    resp = client.post("/complaints", json={"complaint": "bad token"}, headers=_auth_headers("garbage-token"))
    assert resp.status_code == 401


def test_create_and_list_own_complaint():
    auth = _signup(email="complainer@example.com").json()
    resp = client.post(
        "/complaints",
        json={"complaint": "My bill was overcharged this month"},
        headers=_auth_headers(auth["token"]),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["category"] == "Billing"
    assert body["priority"] in ["Low", "Medium", "High"]
    assert body["status"] == "Pending"
    assert body["received_via"] == "Web Form"
    assert body["user_id"] == auth["user"]["user_id"]

    resp = client.get("/complaints", headers=_auth_headers(auth["token"]))
    assert resp.status_code == 200
    assert len(resp.json()) >= 1
    assert all(c["user_id"] == auth["user"]["user_id"] for c in resp.json())


def test_priority_reflects_urgency_not_just_a_constant():
    # Exercises Algorithm 2 at the HTTP layer, not just the underlying
    # function directly - this endpoint never had a priority-specific
    # test before priority prediction existed.
    auth = _signup(email="urgent@example.com").json()
    calm = client.post(
        "/complaints", json={"complaint": "I have a small question about my invoice, not urgent."},
        headers=_auth_headers(auth["token"]),
    ).json()
    urgent = client.post(
        "/complaints",
        json={"complaint": "URGENT!!! This is unacceptable, I have been overcharged for weeks and nobody responds, I am furious!"},
        headers=_auth_headers(auth["token"]),
    ).json()
    assert calm["priority"] == "Low"
    assert urgent["priority"] == "High"


def test_idor_is_fixed_users_cannot_see_each_others_complaints():
    """This is the bug we fixed: user A must never see user B's complaints."""
    auth_a = _signup(email="usera@example.com").json()
    auth_b = _signup(email="userb@example.com").json()

    client.post("/complaints", json={"complaint": "A's private complaint"}, headers=_auth_headers(auth_a["token"]))
    client.post("/complaints", json={"complaint": "B's private complaint"}, headers=_auth_headers(auth_b["token"]))

    resp_a = client.get("/complaints", headers=_auth_headers(auth_a["token"]))
    texts_a = [c["complaint"] for c in resp_a.json()]
    assert "B's private complaint" not in texts_a

    resp_b = client.get("/complaints", headers=_auth_headers(auth_b["token"]))
    texts_b = [c["complaint"] for c in resp_b.json()]
    assert "A's private complaint" not in texts_b


def test_manual_category_overrides_auto_classify():
    auth = _signup(email="manual@example.com").json()
    resp = client.post(
        "/complaints",
        json={"complaint": "totally unrelated text", "category": "Service"},
        headers=_auth_headers(auth["token"]),
    )
    assert resp.json()["category"] == "Service"


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


def test_categories_endpoint():
    resp = client.get("/categories")
    assert resp.status_code == 200
    assert resp.json() == ["Billing", "Financial", "Technical", "Service", "Others"]


def test_chatbot_recommend():
    resp = client.post("/chatbot/recommend", json={"complaint_text": "My internet is down again"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["category"] == "Technical"
    assert "recommendation" in body


# ------------------------------------------------------------- admin ----
# NOTE: this whole section replaces a stale test that called
# GET /admin/complaints with NO auth and expected 200 + a plain list -
# that was true before admin auth existed (see docs/ADMIN_AUTH.md and
# DECISIONS.md #13). It's a 401 now, and the response shape changed to
# a paginated object. Caught and fixed while wiring up CI - see
# docs/DECISIONS.md #18 for why that matters.

def test_admin_complaints_requires_auth():
    resp = client.get("/admin/complaints")
    assert resp.status_code == 401


def test_admin_complaints_rejects_customer_token():
    auth = _signup(email="notadmin@example.com").json()
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
        json={"complaint": "Customer called about a billing dispute", "received_via": "Phone Call"},
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
    # CI doesn't (and shouldn't) have a real GEMINI_API_KEY configured -
    # this confirms the fallback path responds usefully rather than
    # erroring, per app/chatbot.py's design.
    admin = _admin_login()
    resp = client.post(
        "/admin/chatbot/ask", json={"question": "How should I handle a repeat billing complaint?"},
        headers=_auth_headers(admin["token"]),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "answer" in body
    assert isinstance(body["used_rag"], bool)


def test_admin_chatbot_ask_rejects_unknown_ticket():
    admin = _admin_login()
    resp = client.post(
        "/admin/chatbot/ask", json={"question": "What's going on with this ticket?", "ticket_no": 999999},
        headers=_auth_headers(admin["token"]),
    )
    assert resp.status_code == 404
