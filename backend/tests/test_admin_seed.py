import os

from app.admin_seed import ensure_admin_seeded
from app.db import get_collection


def test_ensure_admin_seeded_creates_admin_role_account(monkeypatch):
    monkeypatch.setenv("ADMIN_EMAIL", "test-admin@loopline.io")
    monkeypatch.setenv("ADMIN_USERNAME", "TestAdmin")
    monkeypatch.setenv("ADMIN_PASSWORD", "TestPass1!")

    user_id = ensure_admin_seeded()

    user = get_collection("users").find_one({"user_id": user_id})
    assert user["email"] == "test-admin@loopline.io"
    assert user["role"] == "admin"


def test_ensure_admin_seeded_is_idempotent(monkeypatch):
    monkeypatch.setenv("ADMIN_EMAIL", "idempotent-admin@loopline.io")

    first_id = ensure_admin_seeded()
    second_id = ensure_admin_seeded()

    assert first_id == second_id
    matches = list(get_collection("users").find({"email": "idempotent-admin@loopline.io"}))
    assert len(matches) == 1
