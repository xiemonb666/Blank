from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
from datetime import UTC, datetime
from uuid import uuid4

from .models import UserPublic
from .security import normalize_username, token_storage_key, validate_new_password
from .store import SessionStore


AUTH_DUMMY_PASSWORD = "BlankDummyPassword123"
AUTH_DUMMY_SALT = "0" * 32
AUTH_DUMMY_HASH = ""


def hash_password(password: str, salt: str | None = None) -> str:
    actual_salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), actual_salt.encode("utf-8"), 240_000)
    return f"pbkdf2_sha256${actual_salt}${base64.b64encode(digest).decode('ascii')}"


def verify_password(password: str, password_hash: str) -> bool:
    try:
        algorithm, salt, encoded = password_hash.split("$", 2)
    except ValueError:
        return False
    if algorithm != "pbkdf2_sha256":
        return False
    expected = hash_password(password, salt)
    return hmac.compare_digest(expected, f"{algorithm}${salt}${encoded}")


def register_user(
    store: SessionStore,
    username: str,
    password: str,
    role: str = "learner",
    admin_bootstrap_key: str | None = None,
    allow_learner_registration: bool = True,
) -> UserPublic:
    validate_new_password(password)
    now = datetime.now(UTC).isoformat()

    def role_for_insert(is_first_user: bool) -> str:
        if should_bootstrap_admin(is_first_user, admin_bootstrap_key):
            return "admin"
        if not allow_learner_registration:
            raise ValueError("生产环境已关闭公开注册，请联系管理员创建账号。")
        if role not in {"learner", "org_manager", "org_member"}:
            raise ValueError("注册身份无效。")
        return role

    return store.create_user_atomic(
        user_id=uuid4().hex,
        username=normalize_username(username),
        password_hash=hash_password(password),
        role_factory=role_for_insert,
        is_active=True,
        created_at=now,
    )


def should_bootstrap_admin(is_first_user: bool, provided_key: str | None) -> bool:
    expected_key = os.getenv("BLANK_ADMIN_BOOTSTRAP_KEY", "")
    if not is_first_user or not expected_key:
        return False
    return hmac.compare_digest(provided_key or "", expected_key)


def authenticate_user(store: SessionStore, username: str, password: str) -> UserPublic | None:
    record = store.get_user_password_hash(normalize_username(username))
    if record is None:
        verify_password(password, AUTH_DUMMY_HASH)
        return None
    user, password_hash = record
    if not user.is_active:
        verify_password(password, AUTH_DUMMY_HASH)
        return None
    if not verify_password(password, password_hash):
        return None
    return user


def dummy_password_hash() -> str:
    return hash_password(AUTH_DUMMY_PASSWORD, AUTH_DUMMY_SALT)


AUTH_DUMMY_HASH = dummy_password_hash()


def issue_token(store: SessionStore, user_id: str, remember_me: bool = False) -> str:
    token = secrets.token_urlsafe(32)
    store.create_token(token_storage_key(token), user_id, datetime.now(UTC).isoformat(), remember_me=remember_me)
    return token
