"""
Signup / login logic - mirrors the validation rules already used in
the frontend's auth.js, so both sides behave the same way:
  - username: starts with a letter, 3-20 chars, letters/numbers/spaces
  - email: standard email shape
  - password: 8+ chars, 1 uppercase letter, 1 special char (!@#$%^&*)
"""
import re
from datetime import datetime, timezone

from .security import hash_password

USERNAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9 ]{2,19}$")
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
SPECIAL_RE = re.compile(r"[!@#$%^&*]")


class AuthError(Exception):
    """Raised for a validation problem - the message is safe to show the user."""


def validate_signup(username: str, email: str, password: str) -> None:
    if not USERNAME_RE.match(username):
        raise AuthError("Name must start with a letter and be 3-20 characters (letters, numbers, spaces).")
    if not EMAIL_RE.match(email):
        raise AuthError("Enter a valid email, e.g. you@example.com.")
    if len(password) < 8 or not any(c.isupper() for c in password) or not SPECIAL_RE.search(password):
        raise AuthError("Password needs 8+ characters, one uppercase letter, and one special character (!@#$%^&*).")


def next_user_id(existing_user_ids) -> int:
    return max(existing_user_ids, default=0) + 1


def build_new_user(username: str, email: str, password: str, user_id: int, role: str = "customer") -> dict:
    return {
        "user_id": user_id,
        "username": username,
        "email": email,
        "password_hash": hash_password(password),
        "joined": datetime.now(timezone.utc).isoformat(),
        "role": role,
    }
