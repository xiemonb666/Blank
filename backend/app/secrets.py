from __future__ import annotations

import base64
import hashlib
import errno
import os
import secrets
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken


SECRET_PREFIX = "enc:v1:"
BACKEND_DIR = Path(__file__).resolve().parents[1]


class SecretConfigurationError(RuntimeError):
    pass


def encrypt_secret(value: str, context: Path | str | None = None) -> str:
    if not value:
        return ""
    if value.startswith(SECRET_PREFIX):
        return value
    return SECRET_PREFIX + fernet_for(context).encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_secret(value: str, context: Path | str | None = None) -> str:
    if not value:
        return ""
    if not value.startswith(SECRET_PREFIX):
        return value
    token = value.removeprefix(SECRET_PREFIX).encode("ascii")
    try:
        return fernet_for(context).decrypt(token).decode("utf-8")
    except InvalidToken as exc:
        raise SecretConfigurationError("API Key 解密失败，请检查 BLANK_SECRET_KEY 是否与加密时一致。") from exc


def secret_is_encrypted(value: str) -> bool:
    return value.startswith(SECRET_PREFIX)


def fernet_for(context: Path | str | None = None) -> Fernet:
    key_material = load_secret_key_material(context)
    key = base64.urlsafe_b64encode(hashlib.sha256(key_material.encode("utf-8")).digest())
    return Fernet(key)


def load_secret_key_material(context: Path | str | None = None) -> str:
    configured = os.getenv("BLANK_SECRET_KEY", "")
    if configured:
        if len(configured) < 32:
            raise SecretConfigurationError("BLANK_SECRET_KEY 至少需要 32 个字符。")
        return configured

    if runtime_environment() == "production":
        raise SecretConfigurationError("生产环境必须设置 BLANK_SECRET_KEY。")

    if isinstance(context, Path):
        db_path = context
    else:
        db_path = BACKEND_DIR / "data" / "blank.postgres"
    return load_or_create_local_secret(db_path.parent / ".blank_secret_key")


def load_or_create_local_secret(path: Path) -> str:
    if path.is_symlink():
        raise SecretConfigurationError("本地密钥文件不能是符号链接。")
    if path.exists():
        harden_secret_file(path)
        return path.read_text(encoding="utf-8").strip()

    key = secrets.token_urlsafe(48)
    write_new_secret_file(path, key)
    return key


def write_new_secret_file(path: Path, key: str) -> None:
    if os.name != "posix":
        path.write_text(key, encoding="utf-8")
        harden_secret_file(path)
        return

    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags, 0o600)
    except OSError as exc:
        if exc.errno in {errno.EEXIST, errno.ELOOP} or path.is_symlink():
            raise SecretConfigurationError("本地密钥文件不能是符号链接或已被并发创建。") from exc
        raise
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(key)


def harden_secret_file(path: Path) -> None:
    if os.name != "posix":
        return
    try:
        path.chmod(0o600)
    except OSError:
        return


def runtime_environment() -> str:
    return os.getenv("BLANK_ENV", "development").strip().lower()


def is_production() -> bool:
    return runtime_environment() in {"prod", "production"}
