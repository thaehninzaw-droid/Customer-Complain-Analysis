"""
Minimal session handling.

WHY THIS FILE EXISTS (read this before touching it):
Before this, /complaints trusted whatever user_id the caller sent in
the request. That meant anyone could read or file complaints as any
other user just by guessing a number - this class of bug is called
IDOR (Insecure Direct Object Reference), and it's common enough to be
on the OWASP Top 10 list of web vulnerabilities. The fix: figure out
WHO is calling from something they can't fake (a token only the real
user has), never from a value they typed into the request themselves.

This is intentionally a small, simple version of that idea - an
opaque random token mapped to a user_id, stored in its own "sessions"
collection. It has no expiry and isn't a JWT. A production system
would add both. That's noted as follow-up work in DECISIONS.md rather
than built now, so we spend the limited time before the deadline on
closing the actual hole first.
"""
import secrets

from .db import get_collection


def create_session(user_id: int) -> str:
    """Called right after signup/login succeeds. Returns a token the
    frontend must send back on every request that needs to know who
    the caller is."""
    token = secrets.token_urlsafe(32)
    get_collection("sessions").insert_one({"token": token, "user_id": user_id})
    return token


def get_user_id_for_token(token: str):
    """Returns the user_id for a valid token, or None if the token is
    missing/invalid. Never trust a user_id that came from anywhere
    else for actions that should be tied to 'the logged-in user'."""
    if not token:
        return None
    matches = list(get_collection("sessions").find({"token": token}))
    if not matches:
        return None
    return matches[0]["user_id"]
