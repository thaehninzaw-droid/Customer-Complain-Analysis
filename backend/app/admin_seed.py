"""
Creates (or verifies) a demo admin account. Shared by two callers:
  1. app/main.py's startup hook - runs automatically every time the
     API starts, so local dev with the in-memory DB fallback (no
     MONGODB_URI set) always has a working admin login without any
     extra setup step. Safe to run every startup: it's a no-op if the
     account already exists.
  2. data/seed_admin.py - a standalone script for running this once
     against a real MongoDB Atlas cluster (see docs/DEPLOYMENT.md).

Per the SRS PDF, admin accounts are "log in only" - there's no public
admin signup page/endpoint anywhere in this app. This is the only way
an admin account gets created.

⚠️ SECURITY: the default password below is a placeholder for local
development ONLY. Set ADMIN_EMAIL / ADMIN_USERNAME / ADMIN_PASSWORD in
your real .env (or your deployment platform's env var settings) before
anyone relies on this for anything beyond local testing - see
docs/DEPLOYMENT.md and docs/ADMIN_AUTH.md.
"""
import os

from .auth import build_new_user
from .db import get_collection

DEFAULT_ADMIN_EMAIL = "admin@loopline.io"
DEFAULT_ADMIN_USERNAME = "Admin"
# Meets validate_signup()'s rules (8+ chars, 1 uppercase, 1 special char)
# purely so the same login form/validation works for admin accounts too.
DEFAULT_ADMIN_PASSWORD = "ChangeMe123!"


def ensure_admin_seeded() -> int:
    """Idempotent: does nothing if an account with this email already
    exists. Returns that account's user_id either way."""
    email = os.getenv("ADMIN_EMAIL", DEFAULT_ADMIN_EMAIL)
    username = os.getenv("ADMIN_USERNAME", DEFAULT_ADMIN_USERNAME)
    password = os.getenv("ADMIN_PASSWORD", DEFAULT_ADMIN_PASSWORD)

    users = get_collection("users")
    existing = users.find_one({"email": email})
    if existing:
        return existing["user_id"]

    all_users = list(users.find())
    new_id = max([u["user_id"] for u in all_users], default=0) + 1
    doc = build_new_user(username, email, password, new_id, role="admin")
    users.insert_one(doc)

    using_default_password = "ADMIN_PASSWORD" not in os.environ
    print(f"[loopline] Seeded demo admin account -> email: {email}"
          + (f" | password: {password} (default - set ADMIN_PASSWORD to change)" if using_default_password else " | password: (from ADMIN_PASSWORD env var)"))
    return new_id
