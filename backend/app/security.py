"""Password hashing, password policy and session tokens.

- Passwords: Argon2id via argon2-cffi (maintained library, safe defaults). Plain passwords are never stored or logged.
- Session cookie value: 256-bit random token; only its SHA-256 is stored server-side.
- Policy follows current NIST guidance: length over composition rules, plus a short deny-list.
"""
from __future__ import annotations

import hashlib
import re
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

_hasher = PasswordHasher()
EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(\.[A-Za-z0-9\-]+)+$")
MIN_LEN, MAX_LEN = 10, 128
COMMON = {"password", "password1", "password123", "1234567890", "qwertyuiop", "letmein123", "iloveyou12",
          "admin12345", "welcome123", "changeme123", "0123456789", "abcdefghij", "creditlens"}


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(stored_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(stored_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


# Used so that "unknown email" and "wrong password" take similar time.
DUMMY_HASH = _hasher.hash("not-a-real-password-for-timing")


def normalize_email(email: str) -> str:
    return email.strip().lower()


def password_problems(password: str, email: str = "") -> list[str]:
    problems = []
    if len(password) < MIN_LEN:
        problems.append(f"must be at least {MIN_LEN} characters")
    if len(password) > MAX_LEN:
        problems.append(f"must be at most {MAX_LEN} characters")
    if password.lower() in COMMON:
        problems.append("is too common")
    if len(set(password)) < 4:
        problems.append("is too repetitive")
    local = email.split("@")[0].lower() if email else ""
    if local and len(local) >= 4 and local in password.lower():
        problems.append("must not contain your email name")
    return problems


def new_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
