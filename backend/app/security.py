from __future__ import annotations

import ipaddress
import os
import re
import hashlib
import hmac
import socket
import time
from collections import defaultdict, deque
from threading import Lock
from urllib.parse import urlparse

from fastapi import HTTPException, Request, UploadFile

from .redis_client import clear_redis_rate_limit, redis_rate_limit_check


MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_REQUEST_BYTES = 1024 * 1024
MAX_MULTIPART_REQUEST_BYTES = MAX_UPLOAD_BYTES + 1024 * 1024
TOKEN_TTL_SECONDS = 7 * 24 * 60 * 60
TOKEN_TTL_REMEMBER_SECONDS = 30 * 24 * 60 * 60
SESSION_COOKIE_NAME = "__Host-blank_session"
CSRF_COOKIE_NAME = "__Host-blank_csrf"
LEGACY_SESSION_COOKIE_NAME = "blank_session"
LEGACY_CSRF_COOKIE_NAME = "blank_csrf"
CSRF_PROTECTED_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
RATE_LIMIT_WINDOW_SECONDS = 60
LOGIN_RATE_LIMIT = 20
REGISTER_RATE_LIMIT = 12
DEFAULT_MAX_ACTIVE_TOKENS_PER_USER = 5
DEFAULT_AUDIT_LOG_RETENTION = 5000
DEFAULT_RATE_LIMIT_BUCKETS = 20_000
DEFAULT_PARSE_JOB_RETENTION_PER_USER = 80
DEFAULT_SESSION_RETENTION_PER_USER = 100
DEFAULT_MAX_CONCURRENT_PARSE_JOBS = 2
MODEL_PROXY_FAKE_IP_NETWORKS = tuple(ipaddress.ip_network(item) for item in ("198.18.0.0/15",))
MIN_SUBMITTED_TOKEN_LENGTH = 32
MAX_SUBMITTED_TOKEN_LENGTH = 256
TOKEN_VALUE_PATTERN = re.compile(r"^[A-Za-z0-9._~-]+$")
RESOURCE_ID_PATTERN = re.compile(r"^[a-f0-9]{32}$")
CONTROL_CHARACTER_PATTERN = re.compile(r"[\x00-\x1f\x7f]")
ALLOWED_API_PROVIDERS = {"openai", "vllm", "ollama", "custom"}
OPENAI_COMPATIBLE_PROVIDERS = {"openai", "vllm", "custom"}
TOKEN_STORAGE_PREFIX = "hmac_sha256"
LEGACY_TOKEN_STORAGE_PREFIX = "sha256"

_RATE_BUCKETS: dict[str, deque[float]] = defaultdict(deque)
_RATE_LOCK = Lock()


def cors_origins() -> list[str]:
    configured = os.getenv("BLANK_CORS_ORIGINS", "")
    if configured.strip():
        return [origin.strip() for origin in configured.split(",") if origin.strip()]
    return [
        "http://localhost:5173",
        "http://localhost:5174",
        "http://localhost:5175",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5174",
        "http://127.0.0.1:5175",
        "http://localhost:4173",
        "http://localhost:4174",
        "http://localhost:4175",
        "http://127.0.0.1:4173",
        "http://127.0.0.1:4174",
        "http://127.0.0.1:4175",
    ]


def cors_origins_are_configured() -> bool:
    return bool(os.getenv("BLANK_CORS_ORIGINS", "").strip())


def origin_is_allowed(origin: str | None) -> bool:
    if not origin:
        return False
    return origin in cors_origins()


def fetch_metadata_allows_request(request: Request) -> bool:
    if request.method.upper() not in CSRF_PROTECTED_METHODS:
        return True
    site = request.headers.get("sec-fetch-site", "").strip().lower()
    if not site or site in {"same-origin", "same-site", "none"}:
        return True
    if site == "cross-site":
        return origin_is_allowed(request.headers.get("origin"))
    return False


def cookie_secure_flag() -> bool:
    if environment_flag("BLANK_COOKIE_SECURE"):
        return True
    return os.getenv("BLANK_ENV", "development").strip().lower() in {"prod", "production"}


def cookie_samesite_value() -> str:
    configured = os.getenv("BLANK_COOKIE_SAMESITE", "").strip().lower()
    if configured in {"strict", "lax", "none"}:
        return configured
    return "strict"


def trusted_hosts() -> list[str]:
    configured = os.getenv("BLANK_ALLOWED_HOSTS", "")
    if configured.strip():
        return [host.strip() for host in configured.split(",") if host.strip()]
    return ["localhost", "127.0.0.1", "testserver"]


def trusted_hosts_are_configured() -> bool:
    return bool(os.getenv("BLANK_ALLOWED_HOSTS", "").strip())


def environment_flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def security_headers() -> dict[str, str]:
    headers = {
        "Cache-Control": "no-store",
        "Pragma": "no-cache",
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "X-Permitted-Cross-Domain-Policies": "none",
        "Referrer-Policy": "no-referrer",
        "Permissions-Policy": "camera=(), microphone=(self), geolocation=(), payment=()",
        "Content-Security-Policy": (
            "default-src 'none'; "
            "base-uri 'none'; "
            "form-action 'none'; "
            "frame-ancestors 'none'; "
            "object-src 'none'; "
            "script-src 'none'; "
            "style-src 'none'; "
            "img-src 'none'; "
            "connect-src 'none'"
        ),
        "Cross-Origin-Opener-Policy": "same-origin",
        "Cross-Origin-Resource-Policy": "same-site",
    }
    if os.getenv("BLANK_ENV", "development").strip().lower() in {"prod", "production"}:
        headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
    return headers


async def read_upload_bytes_limited(file: UploadFile, limit: int = MAX_UPLOAD_BYTES) -> bytes:
    raw = await file.read(limit + 1)
    if len(raw) > limit:
        raise HTTPException(status_code=413, detail=f"文件过大，请上传不超过 {limit // 1024 // 1024}MB 的材料。")
    return raw


def client_key(request: Request, scope: str) -> str:
    direct_client_ip = request.client.host if request.client else ""
    client_ip = ""
    if trust_proxy_headers() and client_is_trusted_proxy(direct_client_ip):
        client_ip = forwarded_client_ip(request)
    if not client_ip:
        client_ip = direct_client_ip
    return f"{scope}:{client_ip or 'unknown'}"


def login_rate_keys(request: Request, username: str) -> tuple[str, str]:
    normalized_username = username.strip().lower()
    return client_key(request, "login-ip"), f"login-user:{normalized_username or 'unknown'}"


def trust_proxy_headers() -> bool:
    return environment_flag("BLANK_TRUST_PROXY_HEADERS")


def trusted_proxies_are_configured() -> bool:
    return bool(os.getenv("BLANK_TRUSTED_PROXIES", "").strip())


def trusted_proxy_networks() -> tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...]:
    configured = os.getenv("BLANK_TRUSTED_PROXIES", "").strip()
    if not configured:
        return ()
    networks: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []
    for raw_value in configured.split(","):
        value = raw_value.strip()
        if not value:
            continue
        try:
            networks.append(ipaddress.ip_network(value, strict=False))
        except ValueError as exc:
            raise ValueError("BLANK_TRUSTED_PROXIES 只能包含 IP 或 CIDR，多个值用英文逗号分隔。") from exc
    return tuple(networks)


def client_is_trusted_proxy(client_ip: str) -> bool:
    if not client_ip:
        return False
    try:
        address = ipaddress.ip_address(client_ip)
        networks = trusted_proxy_networks()
    except ValueError:
        return False
    return any(address in network for network in networks)


def forwarded_client_ip(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for", "")
    candidate = forwarded_for.split(",", 1)[0].strip() if forwarded_for else ""
    if not candidate:
        return ""
    try:
        return str(ipaddress.ip_address(candidate))
    except ValueError:
        return ""


def allow_public_registration() -> bool:
    if environment_flag("BLANK_ALLOW_PUBLIC_REGISTRATION"):
        return True
    return os.getenv("BLANK_ENV", "development").strip().lower() not in {"prod", "production"}


def enforce_rate_limit(key: str, limit: int, window_seconds: int = RATE_LIMIT_WINDOW_SECONDS) -> None:
    try:
        allowed = redis_rate_limit_check(key, limit, window_seconds)
    except Exception as exc:
        if not redis_fallback_allowed():
            raise HTTPException(status_code=503, detail="Redis 限流服务不可用，请稍后再试。") from exc
        allowed = False
    if allowed:
        return
    if not redis_fallback_allowed():
        raise HTTPException(status_code=503, detail="Redis 限流服务未配置或不可用。")
    now = time.monotonic()
    cutoff = now - window_seconds
    with _RATE_LOCK:
        prune_rate_buckets(cutoff)
        bucket = _RATE_BUCKETS[key]
        if len(bucket) >= limit:
            raise HTTPException(status_code=429, detail="请求过于频繁，请稍后再试。")
        bucket.append(now)
        prune_rate_bucket_capacity()


def redis_fallback_allowed() -> bool:
    if environment_flag("BLANK_ALLOW_IN_MEMORY_RATE_LIMIT"):
        return True
    return os.getenv("BLANK_ENV", "development").strip().lower() in {"test", "testing"}


def max_rate_limit_buckets() -> int:
    configured = os.getenv("BLANK_MAX_RATE_LIMIT_BUCKETS", "").strip()
    if not configured:
        return DEFAULT_RATE_LIMIT_BUCKETS
    try:
        value = int(configured)
    except ValueError as exc:
        raise ValueError("BLANK_MAX_RATE_LIMIT_BUCKETS 必须是整数。") from exc
    return max(100, min(value, 1_000_000))


def prune_rate_buckets(cutoff: float) -> None:
    empty_keys: list[str] = []
    for key, bucket in _RATE_BUCKETS.items():
        while bucket and bucket[0] < cutoff:
            bucket.popleft()
        if not bucket:
            empty_keys.append(key)
    for key in empty_keys:
        _RATE_BUCKETS.pop(key, None)


def prune_rate_bucket_capacity() -> None:
    overflow = len(_RATE_BUCKETS) - max_rate_limit_buckets()
    if overflow <= 0:
        return
    oldest_keys = sorted(_RATE_BUCKETS, key=lambda item: _RATE_BUCKETS[item][0] if _RATE_BUCKETS[item] else 0)
    for key in oldest_keys[:overflow]:
        _RATE_BUCKETS.pop(key, None)


def clear_rate_limits() -> None:
    with _RATE_LOCK:
        keys = list(_RATE_BUCKETS.keys())
        _RATE_BUCKETS.clear()
    try:
        from .redis_client import get_redis
        r = get_redis()
        if r is not None:
            for key in keys:
                r.delete(key)
    except Exception:
        pass


def validate_model_base_url(base_url: str) -> str:
    normalized = base_url.strip().rstrip("/")
    if not normalized:
        raise ValueError("Base URL 不能为空。")
    if CONTROL_CHARACTER_PATTERN.search(normalized) or any(char.isspace() for char in normalized):
        raise ValueError("Base URL 不允许包含空白或控制字符。")
    parsed = urlparse(normalized)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("Base URL 只允许 http 或 https。")
    if not parsed.hostname:
        raise ValueError("Base URL 缺少主机名。")
    if parsed.username or parsed.password:
        raise ValueError("Base URL 不允许包含用户名或密码。")
    if parsed.query:
        raise ValueError("Base URL 不允许包含查询参数。")
    if parsed.fragment:
        raise ValueError("Base URL 不允许包含 URL 片段。")
    if parsed.scheme == "http" and not allow_insecure_model_url(parsed.hostname):
        raise ValueError("生产环境模型 Base URL 必须使用 https。")
    if not allow_private_model_urls():
        ensure_public_hostname(parsed.hostname)
    return normalized


def validate_api_key_value(api_key: str) -> str:
    normalized = api_key.strip()
    if api_key != normalized:
        raise ValueError("API Key 不能包含首尾空白。")
    if CONTROL_CHARACTER_PATTERN.search(normalized):
        raise ValueError("API Key 不允许包含控制字符。")
    return normalized


def validate_model_identifier(model: str) -> str:
    normalized = model.strip()
    if model != normalized:
        raise ValueError("模型名称不能包含首尾空白。")
    if CONTROL_CHARACTER_PATTERN.search(normalized):
        raise ValueError("模型名称不允许包含控制字符。")
    return normalized


def validate_model_request_parts(base_url: str, api_key: str, model: str) -> tuple[str, str, str]:
    return (
        validate_model_base_url(base_url),
        validate_api_key_value(api_key),
        validate_model_identifier(model),
    )


def validate_api_provider(provider: str) -> str:
    normalized = provider.strip().lower()
    if provider != normalized:
        raise ValueError("Provider 不能包含首尾空白或大写字符。")
    if CONTROL_CHARACTER_PATTERN.search(normalized):
        raise ValueError("Provider 不允许包含控制字符。")
    if normalized not in ALLOWED_API_PROVIDERS:
        allowed = "、".join(sorted(ALLOWED_API_PROVIDERS))
        raise ValueError(f"Provider 仅允许：{allowed}。")
    return normalized


def validate_api_config_parts(provider: str, base_url: str, api_key: str, model: str) -> tuple[str, str, str, str]:
    normalized_provider = validate_api_provider(provider)
    normalized_base_url, normalized_api_key, normalized_model = validate_model_request_parts(base_url, api_key, model)
    if not normalized_model:
        raise ValueError("模型名称不能为空，请显式填写要调用的模型。")
    if normalized_provider in OPENAI_COMPATIBLE_PROVIDERS and not normalized_api_key:
        raise ValueError("OpenAI 兼容接口必须填写 API Key。")
    return normalized_provider, normalized_base_url, normalized_api_key, normalized_model


def allow_private_model_urls() -> bool:
    return environment_flag("BLANK_ALLOW_PRIVATE_MODEL_URLS")


def allow_insecure_model_url(hostname: str) -> bool:
    if allow_private_model_urls():
        return True
    return not is_production_environment() and hostname_is_loopback(hostname)


def ensure_public_hostname(hostname: str) -> None:
    for address in resolve_hostname(hostname):
        ip = ipaddress.ip_address(address)
        if not ip.is_global and not model_private_address_is_allowed(hostname, ip):
            raise ValueError("Base URL 指向内网、本机或保留地址，已阻止以防 SSRF。")


def model_private_address_is_allowed(hostname: str, address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if allow_private_model_urls():
        return True
    if is_production_environment():
        return False
    if hostname_is_loopback(hostname) and address.is_loopback:
        return True
    return hostname_is_domain_name(hostname) and model_address_is_proxy_fake_ip(address)


def model_address_is_proxy_fake_ip(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return any(address in network for network in MODEL_PROXY_FAKE_IP_NETWORKS)


def hostname_is_domain_name(hostname: str) -> bool:
    normalized = hostname.strip().strip("[]").rstrip(".")
    if not normalized:
        return False
    try:
        ipaddress.ip_address(normalized)
        return False
    except ValueError:
        return True


def hostname_is_loopback(hostname: str) -> bool:
    normalized = hostname.strip().lower().strip("[]").rstrip(".")
    if normalized == "localhost" or normalized.endswith(".localhost"):
        return True
    try:
        return ipaddress.ip_address(normalized).is_loopback
    except ValueError:
        return False


def is_production_environment() -> bool:
    return os.getenv("BLANK_ENV", "development").strip().lower() in {"prod", "production"}


def resolve_hostname(hostname: str) -> set[str]:
    try:
        literal = ipaddress.ip_address(hostname)
    except ValueError:
        literal = None
    if literal is not None:
        return {str(literal)}

    try:
        infos = socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ValueError("Base URL 主机名无法解析。") from exc

    addresses = {item[4][0] for item in infos if item and item[4]}
    if not addresses:
        raise ValueError("Base URL 主机名没有可用地址。")
    return addresses


def max_request_bytes() -> int:
    configured = os.getenv("BLANK_MAX_REQUEST_BYTES", "").strip()
    if not configured:
        return MAX_REQUEST_BYTES
    try:
        value = int(configured)
    except ValueError as exc:
        raise ValueError("BLANK_MAX_REQUEST_BYTES 必须是整数。") from exc
    return max(64 * 1024, min(value, MAX_UPLOAD_BYTES))


def max_active_tokens_per_user() -> int:
    configured = os.getenv("BLANK_MAX_ACTIVE_TOKENS_PER_USER", "").strip()
    if not configured:
        return DEFAULT_MAX_ACTIVE_TOKENS_PER_USER
    try:
        value = int(configured)
    except ValueError as exc:
        raise ValueError("BLANK_MAX_ACTIVE_TOKENS_PER_USER 必须是整数。") from exc
    return max(1, min(value, 20))


def audit_log_retention_limit() -> int:
    configured = os.getenv("BLANK_AUDIT_LOG_RETENTION", "").strip()
    if not configured:
        return DEFAULT_AUDIT_LOG_RETENTION
    try:
        value = int(configured)
    except ValueError as exc:
        raise ValueError("BLANK_AUDIT_LOG_RETENTION 必须是整数。") from exc
    return max(100, min(value, 100_000))


def parse_job_retention_per_user() -> int:
    configured = os.getenv("BLANK_PARSE_JOB_RETENTION_PER_USER", "").strip()
    if not configured:
        return DEFAULT_PARSE_JOB_RETENTION_PER_USER
    try:
        value = int(configured)
    except ValueError as exc:
        raise ValueError("BLANK_PARSE_JOB_RETENTION_PER_USER 必须是整数。") from exc
    return max(5, min(value, 500))


def session_retention_per_user() -> int:
    configured = os.getenv("BLANK_SESSION_RETENTION_PER_USER", "").strip()
    if not configured:
        return DEFAULT_SESSION_RETENTION_PER_USER
    try:
        value = int(configured)
    except ValueError as exc:
        raise ValueError("BLANK_SESSION_RETENTION_PER_USER 必须是整数。") from exc
    return max(10, min(value, 1000))


def max_concurrent_parse_jobs() -> int:
    configured = os.getenv("BLANK_MAX_CONCURRENT_PARSE_JOBS", "").strip()
    if not configured:
        return DEFAULT_MAX_CONCURRENT_PARSE_JOBS
    try:
        value = int(configured)
    except ValueError as exc:
        raise ValueError("BLANK_MAX_CONCURRENT_PARSE_JOBS 必须是整数。") from exc
    return max(1, min(value, 20))


def request_size_limit_for(content_type: str | None) -> int:
    media_type = (content_type or "").split(";", 1)[0].strip().lower()
    if media_type == "multipart/form-data":
        return MAX_MULTIPART_REQUEST_BYTES
    return max_request_bytes()


def token_hash_secret_material() -> bytes:
    configured = os.getenv("BLANK_TOKEN_HASH_KEY", "").strip() or os.getenv("BLANK_SECRET_KEY", "").strip()
    if configured:
        return configured.encode("utf-8")
    return b"blank-development-token-hash-key"


def legacy_token_storage_key(token: str) -> str:
    return f"{LEGACY_TOKEN_STORAGE_PREFIX}${hashlib.sha256(token.encode('utf-8')).hexdigest()}"


def token_storage_key(token: str) -> str:
    digest = hmac.new(token_hash_secret_material(), token.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{TOKEN_STORAGE_PREFIX}${digest}"


def accepted_token_storage_keys(token: str) -> tuple[str, str, str]:
    return token_storage_key(token), legacy_token_storage_key(token), token


def submitted_token_is_plausible(token: str) -> bool:
    if len(token) < MIN_SUBMITTED_TOKEN_LENGTH or len(token) > MAX_SUBMITTED_TOKEN_LENGTH:
        return False
    return bool(TOKEN_VALUE_PATTERN.fullmatch(token))


def resource_id_is_valid(value: str) -> bool:
    return bool(RESOURCE_ID_PATTERN.fullmatch(value))


def validate_new_password(password: str) -> None:
    if len(password) < 8:
        raise ValueError("密码至少 8 位。")
    if password != password.strip() or any(char.isspace() for char in password):
        raise ValueError("密码不能包含空格。")
    if not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        raise ValueError("密码必须同时包含字母和数字。")
    weak_values = {"password", "password123", "12345678", "qwerty123", "admin123"}
    if password.lower() in weak_values:
        raise ValueError("密码过于常见，请更换。")


def normalize_username(username: str) -> str:
    return username.strip().lower()


def redact_secret_text(value: str, limit: int = 300) -> str:
    redacted = str(value)
    redacted = re.sub(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+", "Bearer ***", redacted)
    redacted = re.sub(
        r"(?i)\b(api[_-]?key|access[_-]?token|refresh[_-]?token|authorization|password|secret)"
        r"\s*([\"'=:\s]+)\s*([A-Za-z0-9._~+/=-]{4,})",
        r"\1\2***",
        redacted,
    )
    redacted = re.sub(r"\bsk-[A-Za-z0-9._-]{4,}", "sk-***", redacted)
    redacted = re.sub(
        r"(?i)([?&](?:api[_-]?key|access[_-]?token|refresh[_-]?token|token|key|password|secret)=)[^&#\s]+",
        r"\1***",
        redacted,
    )
    redacted = re.sub(r"(?i)\b(https?://)([^/@\s:]+):([^/@\s]+)@", r"\1***:***@", redacted)
    return redacted[:limit]
