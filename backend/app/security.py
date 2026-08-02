"""
Simple password hashing - standard library only, no extra dependency
needed (PBKDF2-HMAC-SHA256 with a random salt per user).

Not as strong as bcrypt/argon2, but a solid, dependency-free choice
for a course project - much better than the plain-text passwords the
frontend demo currently stores in localStorage (fine for a pure
front-end demo, not fine once this is a real backend with a real
database).
"""
import hashlib
import hmac
import os

_ITERATIONS = 100_000


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _ITERATIONS)
    return salt.hex() + ":" + digest.hex()


def verify_password(password: str, stored: str) -> bool:
    try:
        salt_hex, digest_hex = stored.split(":")
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(digest_hex)
    except (ValueError, AttributeError):
        return False
    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _ITERATIONS)
    return hmac.compare_digest(actual, expected)
