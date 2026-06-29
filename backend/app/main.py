from __future__ import annotations

from datetime import UTC, datetime
import ipaddress
from pathlib import Path
from threading import BoundedSemaphore, Event, Thread
from uuid import uuid4
import secrets
import logging
from logging.handlers import RotatingFileHandler
from urllib.parse import urlparse

from fastapi import Cookie, Depends, FastAPI, File, Form, Header, HTTPException, Query, Request, Response, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from fastapi.responses import StreamingResponse

from .auth import authenticate_user, issue_token, register_user
from .debug_logging import log_debug_event, sanitize_debug_text, sanitize_debug_value
from .materials import MaterialParseError, extract_material_text, safe_material_title
from .models import (
    ApiConfig,
    ApiConfigCreateRequest,
    ApiConfigUpdateRequest,
    AuthResponse,
    AuditLogEntry,
    ChatRequest,
    ChatResponse,
    FeynmanAnswerSaveRequest,
    FeynmanAnswerSaveResponse,
    FeynmanFollowUpRequest,
    FeynmanFollowUpResponse,
    FeynmanRequest,
    FeynmanQuestionResponse,
    FeynmanResponse,
    HealthResponse,
    LearningSession,
    LearningSessionPublic,
    LoginRequest,
    NodeSelectRequest,
    ParseJobCreateResponse,
    ParseJobPublic,
    ParseJobStatusResponse,
    PersonaRequest,
    ReauthRequest,
    ResearchBlindReviewExportResponse,
    ResearchDashboardResponse,
    ResearchExperimentExportResponse,
    ResearchExperimentImportRequest,
    ResearchExperimentImportResponse,
    SessionCreateRequest,
    SessionCreateResponse,
    SessionSummary,
    SpeechCapabilitiesResponse,
    SpeechSynthesisRequest,
    SpeechTranscriptionResponse,
    TutorSettings,
    TutorSettingsRequest,
    UserCreateRequest,
    UserPublic,
    UserUpdateRequest,
)
from .speech import (
    MAX_SPEECH_UPLOAD_BYTES,
    SpeechServiceError,
    speech_capabilities,
    synthesize_speech,
    transcribe_audio,
)
from .services import (
    AiChatError,
    AiSplitError,
    chat,
    create_session,
    evaluate_feynman,
    find_node,
    generate_feynman_follow_up,
    generate_feynman_questions,
    messages_for_node,
    prewarm_learning_assets,
    save_feynman_answer,
    select_node,
    set_token_usage_recorder,
    stream_chat_events,
)
from .store import ParseJobCreateBlocked, SessionStore
from .security import (
    LOGIN_RATE_LIMIT,
    LEGACY_SESSION_COOKIE_NAME,
    LEGACY_CSRF_COOKIE_NAME,
    REGISTER_RATE_LIMIT,
    CSRF_PROTECTED_METHODS,
    CSRF_COOKIE_NAME,
    SESSION_COOKIE_NAME,
    TOKEN_TTL_SECONDS,
    TOKEN_TTL_REMEMBER_SECONDS,
    allow_public_registration,
    allow_private_model_urls,
    client_key,
    cookie_samesite_value,
    cookie_secure_flag,
    cors_origins,
    cors_origins_are_configured,
    enforce_rate_limit,
    fetch_metadata_allows_request,
    login_rate_keys,
    max_concurrent_parse_jobs,
    origin_is_allowed,
    read_upload_bytes_limited,
    redact_secret_text,
    request_size_limit_for,
    resource_id_is_valid,
    security_headers,
    submitted_token_is_plausible,
    trust_proxy_headers,
    trusted_proxies_are_configured,
    trusted_proxy_networks,
    trusted_hosts,
    trusted_hosts_are_configured,
)
from .secrets import SecretConfigurationError, is_production
import json
import os
import time
from typing import Any, Awaitable, Callable


BASE_DIR = Path(__file__).resolve().parents[1]
PARSE_SUBMIT_INTERVAL_SECONDS = 5
PARSE_JOB_SEMAPHORE = BoundedSemaphore(max_concurrent_parse_jobs())
SESSION_CREATE_RATE_LIMIT = 12
CHAT_RATE_LIMIT = 60
FEYNMAN_RATE_LIMIT = 20
SPEECH_RATE_LIMIT = 30
ADMIN_WRITE_RATE_LIMIT = 20
ADMIN_REAUTH_MAX_AGE_SECONDS = 10 * 60
REAUTH_RATE_LIMIT = 5
BODY_LIMIT_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
SECURITY_LOGGER_NAME = "blank.security"
WEAK_SECRET_VALUES = {
    "admin",
    "admin123",
    "blank",
    "bootstrap",
    "bootstrap-secret",
    "change-this",
    "changeme",
    "default",
    "example",
    "password",
    "password123",
    "secret",
    "test",
}
WEAK_SECRET_PREFIXES = ("change-this", "changeme", "example-")


def validate_startup_security() -> None:
    if not is_production():
        return
    validate_production_secret("BLANK_SECRET_KEY", min_length=32)
    validate_production_secret("BLANK_ADMIN_BOOTSTRAP_KEY", min_length=24)
    if os.getenv("BLANK_TOKEN_HASH_KEY", "").strip():
        validate_production_secret("BLANK_TOKEN_HASH_KEY", min_length=32)
    if not trusted_hosts_are_configured() or "*" in trusted_hosts():
        raise RuntimeError("生产环境必须显式配置 BLANK_ALLOWED_HOSTS，且不能使用通配 Host。")
    origins = cors_origins()
    if not cors_origins_are_configured() or "*" in origins:
        raise RuntimeError("生产环境必须显式配置 BLANK_CORS_ORIGINS，且不能使用通配 CORS。")
    validate_production_cors_origins(origins)
    if not cookie_secure_flag():
        raise RuntimeError("生产环境 Cookie 必须启用 Secure。")
    if cookie_samesite_value() == "none":
        raise RuntimeError("生产环境 Cookie SameSite 不能设置为 none。")
    if allow_private_model_urls():
        raise RuntimeError("生产环境不能开启 BLANK_ALLOW_PRIVATE_MODEL_URLS。")
    if trust_proxy_headers():
        if not trusted_proxies_are_configured():
            raise RuntimeError("生产环境开启 BLANK_TRUST_PROXY_HEADERS 时必须配置 BLANK_TRUSTED_PROXIES。")
        try:
            trusted_proxy_networks()
        except ValueError as exc:
            raise RuntimeError(str(exc)) from exc


def validate_production_secret(name: str, min_length: int) -> None:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"生产环境必须设置 {name}。")
    if len(value) < min_length:
        raise RuntimeError(f"生产环境 {name} 长度不能少于 {min_length} 个字符。")
    normalized = value.lower()
    if normalized in WEAK_SECRET_VALUES or any(normalized.startswith(prefix) for prefix in WEAK_SECRET_PREFIXES):
        raise RuntimeError(f"生产环境 {name} 不能使用示例值、占位符或弱口令。")


def validate_production_cors_origins(origins: list[str]) -> None:
    for origin in origins:
        validate_production_origin(origin)


def validate_production_origin(origin: str) -> None:
    parsed = urlparse(origin)
    if parsed.scheme != "https":
        raise RuntimeError("生产环境 BLANK_CORS_ORIGINS 必须使用 https。")
    if not parsed.hostname or not parsed.netloc:
        raise RuntimeError("生产环境 BLANK_CORS_ORIGINS 必须是完整的 https origin。")
    if parsed.username or parsed.password:
        raise RuntimeError("生产环境 BLANK_CORS_ORIGINS 不能包含用户名或密码。")
    if parsed.path not in {"", "/"} or parsed.params or parsed.query or parsed.fragment:
        raise RuntimeError("生产环境 BLANK_CORS_ORIGINS 只能配置 origin，不能包含路径、查询或片段。")
    hostname = parsed.hostname.lower().rstrip(".")
    if hostname in {"localhost"} or hostname.endswith(".localhost"):
        raise RuntimeError("生产环境 BLANK_CORS_ORIGINS 不能指向 localhost。")
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        return
    if not address.is_global:
        raise RuntimeError("生产环境 BLANK_CORS_ORIGINS 不能指向内网、本机或保留地址。")


def create_app() -> FastAPI:
    return FastAPI(
        title="Blank API",
        version="0.1.0",
        description="Learning workflow API for Blank's input-graph-flow-feynman loop.",
        docs_url=None if is_production() else "/docs",
        redoc_url=None if is_production() else "/redoc",
        openapi_url=None if is_production() else "/openapi.json",
    )


def database_path() -> str:
    configured_db_url = os.getenv("BLANK_DATABASE_URL", "").strip()
    if configured_db_url:
        return configured_db_url
    return "postgresql://blank:blank@127.0.0.1:5432/blank"


def configure_security_logger() -> logging.Logger:
    logger = logging.getLogger(SECURITY_LOGGER_NAME)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    if logger.handlers:
        return logger
    log_path = Path(os.getenv("BLANK_SECURITY_LOG_PATH", str(BASE_DIR / "data" / "security.log"))).expanduser()
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        if os.name == "posix":
            log_path.parent.chmod(0o700)
        handler: logging.Handler = RotatingFileHandler(
            log_path,
            maxBytes=2 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        if os.name == "posix" and log_path.exists():
            log_path.chmod(0o600)
    except OSError:
        handler = logging.NullHandler()
    handler.setFormatter(logging.Formatter("%(asctime)sZ %(message)s"))
    logger.addHandler(handler)
    return logger


def close_security_logger_handlers() -> None:
    logger = logging.getLogger(SECURITY_LOGGER_NAME)
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()


security_logger = configure_security_logger()


def log_security_event(action: str, request: Request, actor: UserPublic | None = None, detail: dict[str, object] | None = None) -> None:
    ip_value = client_key(request, "security").split(":", 1)[1]
    parts = [
        f"event={action}",
        f"ip={ip_value}",
        f"actor_user_id={actor.id if actor else '-'}",
    ]
    for key, value in (detail or {}).items():
        if key.lower() in {"password", "token", "authorization", "api_key", "secret"}:
            continue
        safe_value = redact_secret_text(str(value), limit=120).replace("\n", " ")
        parts.append(f"{key}={safe_value or '-'}")
    security_logger.info(" ".join(parts))


class RequestSizeLimitMiddleware:
    def __init__(self, app: Callable[[dict[str, Any], Callable[[], Awaitable[dict[str, Any]]], Callable[[dict[str, Any]], Awaitable[None]]], Awaitable[None]]):
        self.app = app

    async def __call__(
        self,
        scope: dict[str, Any],
        receive: Callable[[], Awaitable[dict[str, Any]]],
        send: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        content_type = headers.get(b"content-type", b"").decode("latin1")
        limit = request_size_limit_for(content_type)
        content_length = headers.get(b"content-length")
        if content_length:
            try:
                requested_bytes = int(content_length.decode("latin1"))
            except ValueError:
                await self._send_json(send, 400, "Content-Length 无效。")
                return
            if requested_bytes > limit:
                await self._send_json(send, 413, "请求体过大。")
                return
        response_status: int | None = None
        response_headers: dict[str, str] = {}
        response_chunks: list[bytes] = []
        response_bytes = 0

        async def logging_send(message: dict[str, Any]) -> None:
            nonlocal response_status, response_headers, response_bytes
            if message.get("type") == "http.response.start":
                response_status = int(message.get("status", 0) or 0)
                response_headers = {
                    key.decode("latin1").lower(): value.decode("latin1")
                    for key, value in message.get("headers", [])
                    if isinstance(key, bytes) and isinstance(value, bytes)
                }
            elif message.get("type") == "http.response.body":
                body = message.get("body", b"")
                if isinstance(body, bytes) and body:
                    response_bytes += len(body)
                    captured_bytes = sum(len(chunk) for chunk in response_chunks)
                    if captured_bytes < 12_000:
                        response_chunks.append(body[: max(0, 12_000 - captured_bytes)])
            await send(message)

        async def log_response_after_app(app_receive: Callable[[], Awaitable[dict[str, Any]]]) -> None:
            try:
                await self.app(scope, app_receive, logging_send)
            finally:
                if response_status is not None:
                    response_content_type = response_headers.get("content-type", "")
                    log_debug_event(
                        "http.response.body",
                        method=scope.get("method", ""),
                        path=scope.get("path", ""),
                        status_code=response_status,
                        bytes=response_bytes,
                        content_type=response_content_type,
                        body=debug_response_preview(response_content_type, b"".join(response_chunks), response_bytes),
                    )

        if scope.get("method", "").upper() not in BODY_LIMIT_METHODS:
            await log_response_after_app(receive)
            return

        messages: list[dict[str, Any]] = []
        received_bytes = 0
        while True:
            message = await receive()
            if message["type"] != "http.request":
                messages.append(message)
                break
            body = message.get("body", b"")
            received_bytes += len(body)
            if received_bytes > limit:
                await self._send_json(send, 413, "请求体过大。")
                return
            messages.append(message)
            if not message.get("more_body", False):
                break

        body_preview = b"".join(
            item.get("body", b"")
            for item in messages
            if item.get("type") == "http.request" and isinstance(item.get("body", b""), bytes)
        )
        if body_preview:
            log_debug_event(
                "http.request.body",
                method=scope.get("method", ""),
                path=scope.get("path", ""),
                bytes=len(body_preview),
                content_type=content_type,
                body=debug_body_preview(content_type, body_preview),
            )

        async def replay_receive() -> dict[str, Any]:
            if messages:
                return messages.pop(0)
            return await receive()
        await log_response_after_app(replay_receive)

    @staticmethod
    async def _send_json(send: Callable[[dict[str, Any]], Awaitable[None]], status_code: int, detail: str) -> None:
        body = json.dumps({"detail": detail}, ensure_ascii=False).encode("utf-8")
        await send(
            {
                "type": "http.response.start",
                "status": status_code,
                "headers": [
                    (b"content-type", b"application/json; charset=utf-8"),
                    (b"content-length", str(len(body)).encode("ascii")),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body, "more_body": False})


def debug_body_preview(content_type: str, body: bytes) -> object:
    if "multipart/form-data" in content_type:
        return f"[multipart body omitted, {len(body)} bytes]"
    if "application/octet-stream" in content_type:
        return f"[binary body omitted, {len(body)} bytes]"
    text = body.decode("utf-8", errors="replace")
    try:
        return sanitize_debug_value(json.loads(text))
    except json.JSONDecodeError:
        return sanitize_debug_text(text, limit=4000)


def debug_response_preview(content_type: str, body: bytes, total_bytes: int) -> object:
    if not body:
        return ""
    if "application/json" not in content_type and "text/" not in content_type and "application/x-ndjson" not in content_type:
        return f"[response body omitted, {total_bytes} bytes]"
    text = body.decode("utf-8", errors="replace")
    suffix = "" if len(body) >= total_bytes else f"...[truncated {total_bytes - len(body)} bytes]"
    try:
        return sanitize_debug_value(json.loads(text))
    except json.JSONDecodeError:
        return sanitize_debug_text(text + suffix, limit=12_000)


validate_startup_security()
store = SessionStore(database_path())
set_token_usage_recorder(store.record_token_usage)
store.release_stale_parse_jobs()

app = create_app()

app.add_middleware(RequestSizeLimitMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins(),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-CSRF-Token"],
)

app.add_middleware(TrustedHostMiddleware, allowed_hosts=trusted_hosts(), www_redirect=False)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_: Request, exc: RequestValidationError):
    details = []
    for error in exc.errors():
        details.append(
            {
                "loc": [str(item) for item in error.get("loc", [])],
                "msg": redact_secret_text(str(error.get("msg", "输入格式不正确")), limit=160),
                "type": str(error.get("type", "validation_error")),
            }
        )
    return JSONResponse(status_code=422, content={"detail": details})


@app.middleware("http")
async def enforce_fetch_metadata(request: Request, call_next):
    if request.method.upper() in CSRF_PROTECTED_METHODS:
        origin = request.headers.get("origin")
        if origin and not origin_is_allowed(origin):
            return JSONResponse(status_code=403, content={"detail": "请求来源未通过校验"})
    if not fetch_metadata_allows_request(request):
        return JSONResponse(status_code=403, content={"detail": "跨站请求已被安全策略阻止。"})
    return await call_next(request)


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    start = time.perf_counter()
    request_id = uuid4().hex
    log_debug_event(
        "http.request",
        request_id=request_id,
        method=request.method,
        path=request.url.path,
        query=str(request.url.query),
        client=request.client.host if request.client else "",
        headers=debug_request_headers(request),
    )
    response = await call_next(request)
    duration_ms = round((time.perf_counter() - start) * 1000, 2)
    log_debug_event(
        "http.response",
        request_id=request_id,
        method=request.method,
        path=request.url.path,
        status_code=response.status_code,
        duration_ms=duration_ms,
        content_type=response.headers.get("content-type", ""),
    )
    for name, value in security_headers().items():
        response.headers.setdefault(name, value)
    if "server" in response.headers:
        del response.headers["server"]
    return response


def debug_request_headers(request: Request) -> dict[str, str]:
    return {
        key: sanitize_debug_value({key: value}, limit=500)[key]
        for key, value in request.headers.items()
    }


def set_session_cookie(response: Response, token: str, remember_me: bool = False) -> None:
    csrf_token = secrets.token_urlsafe(32)
    max_age = TOKEN_TTL_REMEMBER_SECONDS if remember_me else TOKEN_TTL_SECONDS
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        max_age=max_age,
        httponly=True,
        secure=cookie_secure_flag(),
        samesite=cookie_samesite_value(),
        path="/",
    )
    response.set_cookie(
        key=CSRF_COOKIE_NAME,
        value=csrf_token,
        max_age=max_age,
        httponly=False,
        secure=cookie_secure_flag(),
        samesite=cookie_samesite_value(),
        path="/",
    )
    if cookie_secure_flag():
        response.delete_cookie(
            key=LEGACY_SESSION_COOKIE_NAME,
            httponly=True,
            secure=cookie_secure_flag(),
            samesite=cookie_samesite_value(),
            path="/",
        )
        response.delete_cookie(
            key=LEGACY_CSRF_COOKIE_NAME,
            httponly=False,
            secure=cookie_secure_flag(),
            samesite=cookie_samesite_value(),
            path="/",
        )
        return
    response.set_cookie(
        key=LEGACY_SESSION_COOKIE_NAME,
        value=token,
        max_age=max_age,
        httponly=True,
        secure=False,
        samesite=cookie_samesite_value(),
        path="/",
    )
    response.set_cookie(
        key=LEGACY_CSRF_COOKIE_NAME,
        value=csrf_token,
        max_age=max_age,
        httponly=False,
        secure=False,
        samesite=cookie_samesite_value(),
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        httponly=True,
        secure=cookie_secure_flag(),
        samesite=cookie_samesite_value(),
        path="/",
    )
    response.delete_cookie(
        key=CSRF_COOKIE_NAME,
        httponly=False,
        secure=cookie_secure_flag(),
        samesite=cookie_samesite_value(),
        path="/",
    )
    response.delete_cookie(
        key=LEGACY_SESSION_COOKIE_NAME,
        httponly=True,
        secure=cookie_secure_flag(),
        samesite=cookie_samesite_value(),
        path="/",
    )
    response.delete_cookie(
        key=LEGACY_CSRF_COOKIE_NAME,
        httponly=False,
        secure=cookie_secure_flag(),
        samesite=cookie_samesite_value(),
        path="/",
    )


def require_token(
    request: Request,
    authorization: str | None = Header(default=None),
    csrf_header: str | None = Header(default=None, alias="X-CSRF-Token"),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    csrf_cookie: str | None = Cookie(default=None, alias=CSRF_COOKIE_NAME),
    legacy_session_cookie: str | None = Cookie(default=None, alias=LEGACY_SESSION_COOKIE_NAME),
    legacy_csrf_cookie: str | None = Cookie(default=None, alias=LEGACY_CSRF_COOKIE_NAME),
) -> str:
    token_source = "header"
    token = ""
    if authorization and authorization.startswith("Bearer "):
        token = authorization.removeprefix("Bearer ").strip()
    elif session_cookie:
        token_source = "cookie"
        token = session_cookie.strip()
    elif legacy_session_cookie and not is_production():
        token_source = "cookie"
        token = legacy_session_cookie.strip()
    else:
        raise HTTPException(status_code=401, detail="请先登录")
    if not token or not submitted_token_is_plausible(token):
        raise HTTPException(status_code=401, detail="请先登录")
    if token_source == "cookie" and request.method.upper() in CSRF_PROTECTED_METHODS:
        origin = request.headers.get("origin")
        if not origin_is_allowed(origin):
            raise HTTPException(status_code=403, detail="请求来源未通过校验")
        expected_csrf = csrf_cookie or (legacy_csrf_cookie if not is_production() else None)
        if not csrf_header or not expected_csrf or not secrets.compare_digest(csrf_header, expected_csrf):
            raise HTTPException(status_code=403, detail="CSRF 校验失败，请刷新页面后重试")
    return token


def require_user(token: str = Depends(require_token)) -> UserPublic:
    user = store.get_user_by_token(token)
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="登录状态已失效")
    return user


def require_admin(user: UserPublic = Depends(require_user)) -> UserPublic:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user


def require_recent_admin_reauth(
    token: str = Depends(require_token),
    admin: UserPublic = Depends(require_admin),
) -> UserPublic:
    if not store.token_recently_reauthenticated(token, ADMIN_REAUTH_MAX_AGE_SECONDS):
        raise HTTPException(status_code=403, detail="需要重新验证管理员密码")
    return admin


def public_session_for_user(session: LearningSession, user: UserPublic) -> LearningSessionPublic:
    return LearningSessionPublic.from_session(session, include_model_metadata=user.role == "admin")


def enforce_admin_write_limit(admin: UserPublic, scope: str) -> None:
    enforce_rate_limit(f"admin-write:{scope}:{admin.id}", ADMIN_WRITE_RATE_LIMIT)


def active_api_config_or_error() -> dict[str, str] | None:
    try:
        config = store.get_active_api_config_secret_record()
    except (SecretConfigurationError, ValueError) as exc:
        raise AiSplitError(f"API 配置不可用：{redact_secret_text(str(exc))}") from exc
    if config is None:
        raise AiSplitError("未启用 API 配置，无法执行 LLM 拆分、对话或评分。请先在后台管理配置并启用模型。")
    return config


def active_api_config_for_chat() -> dict[str, str] | None:
    try:
        return active_api_config_or_error()
    except AiSplitError as exc:
        raise AiChatError(str(exc)) from exc


def active_api_config_for_feynman() -> dict[str, str]:
    try:
        return active_api_config_or_error()
    except AiSplitError as exc:
        raise HTTPException(status_code=502, detail=redact_secret_text(str(exc))) from exc


def require_resource_id(value: str, label: str = "资源") -> str:
    if not resource_id_is_valid(value):
        raise HTTPException(status_code=404, detail=f"{label}不存在")
    return value


def now_iso() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat()


def require_trusted_origin_for_cookie_issue(request: Request) -> None:
    if not origin_is_allowed(request.headers.get("origin")):
        raise HTTPException(status_code=403, detail="请求来源未通过校验")


@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(ok=True, service="blank-api")


@app.get("/api/speech/capabilities", response_model=SpeechCapabilitiesResponse)
def get_speech_capabilities(user: UserPublic = Depends(require_user)) -> SpeechCapabilitiesResponse:
    del user
    return speech_capabilities()


@app.post("/api/speech/asr/transcribe", response_model=SpeechTranscriptionResponse)
async def transcribe_speech(
    file: UploadFile = File(...),
    language: str | None = Form(default=None),
    prompt: str | None = Form(default=None),
    user: UserPublic = Depends(require_user),
) -> SpeechTranscriptionResponse:
    enforce_rate_limit(f"speech-asr:{user.id}", SPEECH_RATE_LIMIT)
    raw = await read_upload_bytes_limited(file, MAX_SPEECH_UPLOAD_BYTES)
    try:
        response = transcribe_audio(
            raw,
            filename=file.filename or "recording.webm",
            content_type=file.content_type or "application/octet-stream",
            language=language,
            prompt=prompt,
        )
    except SpeechServiceError as exc:
        log_debug_event("speech.asr.error", user_id=user.id, error=str(exc))
        raise HTTPException(status_code=502, detail=redact_secret_text(str(exc), limit=220)) from exc
    return response


@app.post("/api/speech/tts")
def synthesize_speech_route(
    payload: SpeechSynthesisRequest,
    user: UserPublic = Depends(require_user),
):
    enforce_rate_limit(f"speech-tts:{user.id}", SPEECH_RATE_LIMIT)
    try:
        result = synthesize_speech(payload.text, voice=payload.voice, language=payload.language)
    except SpeechServiceError as exc:
        log_debug_event("speech.tts.error", user_id=user.id, error=str(exc))
        raise HTTPException(status_code=502, detail=redact_secret_text(str(exc), limit=220)) from exc
    return StreamingResponse(
        iter([result.audio]),
        media_type=result.content_type,
        headers={
            "Content-Length": str(len(result.audio)),
            "X-Blank-Speech-Provider": result.provider,
            "X-Blank-Speech-Voice": result.voice or "",
        },
    )


@app.post("/api/auth/register", response_model=AuthResponse)
def register(payload: UserCreateRequest, request: Request, response: Response) -> AuthResponse:
    require_trusted_origin_for_cookie_issue(request)
    enforce_rate_limit(client_key(request, "register"), REGISTER_RATE_LIMIT)
    existing_users = store.list_users()
    has_valid_admin_bootstrap = can_bootstrap_first_admin(existing_users, payload.admin_bootstrap_key)
    if not allow_public_registration() and not has_valid_admin_bootstrap:
        raise HTTPException(status_code=403, detail="生产环境已关闭公开注册，请联系管理员创建账号。")
    if store.get_user_password_hash(payload.username) is not None:
        raise HTTPException(status_code=409, detail="该账号无法注册")
    try:
        user = register_user(
            store,
            payload.username,
            payload.password,
            payload.admin_bootstrap_key,
            allow_learner_registration=allow_public_registration(),
        )
    except ValueError as exc:
        if "公开注册" in str(exc):
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    token = issue_token(store, user.id, remember_me=bool(payload.remember_me))
    set_session_cookie(response, token, remember_me=bool(payload.remember_me))
    audit_event(user, "auth.register", "user", user.id)
    return AuthResponse(user=user)


def can_bootstrap_first_admin(existing_users: list[UserPublic], provided_key: str | None) -> bool:
    expected = os.getenv("BLANK_ADMIN_BOOTSTRAP_KEY", "")
    return not existing_users and bool(expected) and provided_key == expected


@app.post("/api/auth/login", response_model=AuthResponse)
def login(payload: LoginRequest, request: Request, response: Response) -> AuthResponse:
    require_trusted_origin_for_cookie_issue(request)
    ip_key, username_key = login_rate_keys(request, payload.username)
    enforce_rate_limit(ip_key, LOGIN_RATE_LIMIT)
    enforce_rate_limit(username_key, 8)
    user = authenticate_user(store, payload.username, payload.password)
    if user is None:
        existing = store.get_user_password_hash(payload.username)
        if existing is not None:
            log_security_event("auth.login.failed", request, existing[0], {"source": client_key(request, "login")})
            audit_event(existing[0], "auth.login.failed", "user", existing[0].id, {"source": client_key(request, "login")})
        else:
            log_security_event("auth.login.failed", request, None, {"source": client_key(request, "login")})
        raise HTTPException(status_code=401, detail="账号或凭证无效")
    token = issue_token(store, user.id, remember_me=bool(payload.remember_me))
    set_session_cookie(response, token, remember_me=bool(payload.remember_me))
    audit_event(user, "auth.login", "user", user.id)
    return AuthResponse(user=user)


@app.post("/api/auth/logout")
def logout(response: Response, token: str = Depends(require_token)) -> dict[str, bool]:
    user = store.get_user_by_token(token)
    store.delete_token(token)
    clear_session_cookie(response)
    if user is not None:
        audit_event(user, "auth.logout", "user", user.id)
    return {"ok": True}


@app.post("/api/auth/reauth", response_model=UserPublic)
def reauthenticate(
    payload: ReauthRequest,
    request: Request,
    token: str = Depends(require_token),
    user: UserPublic = Depends(require_user),
) -> UserPublic:
    enforce_rate_limit(client_key(request, "reauth-ip"), REAUTH_RATE_LIMIT)
    enforce_rate_limit(f"reauth-user:{user.id}", REAUTH_RATE_LIMIT)
    authenticated = authenticate_user(store, user.username, payload.password)
    if authenticated is None or authenticated.id != user.id:
        log_security_event("auth.reauth.failed", request, user)
        audit_event(user, "auth.reauth.failed", "user", user.id)
        raise HTTPException(status_code=401, detail="密码验证失败")
    store.mark_token_reauthenticated(token, now_iso())
    audit_event(user, "auth.reauth", "user", user.id)
    return user


@app.get("/api/me", response_model=UserPublic)
def me(user: UserPublic = Depends(require_user)) -> UserPublic:
    return user


@app.get("/api/sessions", response_model=list[SessionSummary])
def list_sessions(user: UserPublic = Depends(require_user)) -> list[SessionSummary]:
    if user.role == "admin":
        return store.list()
    return store.list(user.id)


@app.post("/api/sessions", response_model=SessionCreateResponse)
def create_learning_session(
    payload: SessionCreateRequest,
    user: UserPublic = Depends(require_user),
) -> SessionCreateResponse:
    enforce_rate_limit(f"session-create:{user.id}", SESSION_CREATE_RATE_LIMIT)
    try:
        ai_config = active_api_config_or_error()
        session = create_session(payload.title, payload.content, user.id, ai_config)
    except AiSplitError as exc:
        raise HTTPException(status_code=502, detail=redact_secret_text(str(exc))) from exc
    store.save_session(session)
    audit_event(user, "session.create", "session", session.id, {"title": session.material_title})
    return SessionCreateResponse(session=public_session_for_user(session, user))


@app.post("/api/parse-jobs", response_model=ParseJobCreateResponse)
def create_parse_job(
    payload: SessionCreateRequest,
    user: UserPublic = Depends(require_user),
) -> ParseJobCreateResponse:
    return start_parse_job(payload.title, payload.content, user)


@app.post("/api/parse-jobs/upload", response_model=ParseJobCreateResponse)
async def create_upload_parse_job(
    file: UploadFile = File(...),
    user: UserPublic = Depends(require_user),
) -> ParseJobCreateResponse:
    raw = await read_upload_bytes_limited(file)
    title = safe_material_title(file.filename)
    log_debug_event(
        "parse.upload.received",
        user_id=user.id,
        filename=file.filename,
        safe_title=title,
        content_type=file.content_type,
        bytes=len(raw),
    )
    try:
        content = extract_material_text(title, file.content_type, raw)
    except MaterialParseError as exc:
        log_debug_event("parse.upload.extract_failed", user_id=user.id, title=title, error=str(exc))
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    log_debug_event(
        "parse.upload.extracted",
        user_id=user.id,
        title=title,
        chars=len(content),
        preview=sanitize_debug_text(content, limit=1200),
    )
    return start_parse_job(title, content, user)


def start_parse_job(title: str, content: str, user: UserPublic) -> ParseJobCreateResponse:
    enforce_rate_limit(f"parse-job:{user.id}", SESSION_CREATE_RATE_LIMIT)

    timestamp = now_iso()
    try:
        job = store.create_parse_job_guarded(
            job_id=uuid4().hex,
            user_id=user.id,
            title=title,
            content=content,
            created_at=timestamp,
            min_submit_interval_seconds=PARSE_SUBMIT_INTERVAL_SECONDS,
        )
    except ParseJobCreateBlocked as exc:
        log_debug_event(
            "parse.job.blocked",
            user_id=user.id,
            reason=exc.reason,
            existing_job_id=exc.job.id,
            existing_status=exc.job.status,
            existing_progress=exc.job.progress,
        )
        if exc.reason == "running":
            raise HTTPException(status_code=409, detail={"message": "已有解析任务正在进行", "job_id": exc.job.id}) from exc
        raise HTTPException(
            status_code=429,
            detail={
                "message": f"提交过于频繁，请至少间隔 {PARSE_SUBMIT_INTERVAL_SECONDS} 秒",
                "job_id": exc.job.id,
            },
        ) from exc
    audit_event(user, "parse_job.create", "parse_job", job.id, {"title": title})
    log_debug_event(
        "parse.job.created",
        job_id=job.id,
        user_id=user.id,
        title=title,
        content_chars=len(content),
        content_preview=sanitize_debug_text(content, limit=1600),
    )
    Thread(target=run_parse_job, args=(job.id,), daemon=True).start()
    return ParseJobCreateResponse(job=ParseJobPublic.from_job(job))


def index_session_graphrag(session: LearningSession, content: str, ai_config: dict[str, str]) -> str:
    try:
        from .services_v2.neo4j_service import extract_and_store_knowledge
        from .services_v2.vector_service import chunk_and_store

        entity_result = extract_and_store_knowledge(
            content,
            ai_config,
            tenant_id=session.user_id,
            user_id=session.user_id,
            session_id=session.id,
            source_id=session.id,
        )
        chunk_result = chunk_and_store(
            content,
            session.id,
            ai_config,
            tenant_id=session.user_id,
            user_id=session.user_id,
            session_id=session.id,
        )
        message = (
            f"GraphRAG 已索引：{entity_result.get('entities', 0)} 个实体、"
            f"{entity_result.get('relations', 0)} 条关系、{chunk_result.get('chunks', 0)} 个向量片段"
        )
        log_debug_event(
            "graphrag.index.completed",
            session_id=session.id,
            entity_result=entity_result,
            chunk_result=chunk_result,
        )
        return message
    except Exception as exc:
        safe_detail = redact_secret_text(str(exc), limit=180)
        log_debug_event("graphrag.index.failed", session_id=session.id, error=safe_detail)
        return f"GraphRAG 索引回退：{safe_detail}"


@app.get("/api/parse-jobs/{job_id}", response_model=ParseJobStatusResponse)
def get_parse_job(job_id: str, user: UserPublic = Depends(require_user)) -> ParseJobStatusResponse:
    job_id = require_resource_id(job_id, "解析任务")
    job = store.get_parse_job(job_id, None if user.role == "admin" else user.id)
    if job is None:
        log_debug_event("parse.job.get_missing", job_id=job_id, user_id=user.id, role=user.role)
        raise HTTPException(status_code=404, detail="解析任务不存在")
    session = store.get_session(job.session_id, None if user.role == "admin" else user.id) if job.session_id else None
    if job.status == "completed" and job.session_id and session is None:
        log_debug_event("parse.job.completed_missing_session", job_id=job.id, session_id=job.session_id)
        job = store.update_parse_job(
            job.id,
            "failed",
            100,
            "解析结果保存异常",
            now_iso(),
            session_id=None,
            error="解析任务已完成，但学习记录不存在。请重新上传解析。",
        ) or job
    return ParseJobStatusResponse(
        job=ParseJobPublic.from_job(job),
        session=public_session_for_user(session, user) if session else None,
    )


@app.post("/api/sessions/upload", response_model=SessionCreateResponse)
async def upload_learning_material(
    file: UploadFile = File(...),
    user: UserPublic = Depends(require_user),
) -> SessionCreateResponse:
    raise HTTPException(status_code=410, detail="同步上传接口已关闭，请使用 /api/parse-jobs/upload。")


@app.get("/api/sessions/{session_id}", response_model=LearningSessionPublic)
def get_session(session_id: str, user: UserPublic = Depends(require_user)) -> LearningSessionPublic:
    session_id = require_resource_id(session_id, "会话")
    return public_session_for_user(require_session(session_id, user), user)


@app.delete("/api/sessions/{session_id}")
def delete_session(session_id: str, user: UserPublic = Depends(require_user)) -> dict[str, bool]:
    session_id = require_resource_id(session_id, "会话")
    deleted = store.delete_session(session_id, None if user.role == "admin" else user.id)
    if not deleted:
        raise HTTPException(status_code=404, detail="会话不存在")
    audit_event(user, "session.delete", "session", session_id)
    return {"ok": True}


@app.post("/api/sessions/{session_id}/select-node", response_model=LearningSessionPublic)
def select_session_node(
    session_id: str,
    payload: NodeSelectRequest,
    user: UserPublic = Depends(require_user),
) -> LearningSessionPublic:
    session_id = require_resource_id(session_id, "会话")
    session = require_session(session_id, user)
    try:
        updated = select_node(session, payload.node_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    store.save_session(updated)
    return public_session_for_user(updated, user)


@app.patch("/api/sessions/{session_id}/persona", response_model=LearningSessionPublic)
def update_session_persona(
    session_id: str,
    payload: PersonaRequest,
    user: UserPublic = Depends(require_user),
) -> LearningSessionPublic:
    session_id = require_resource_id(session_id, "会话")
    return save_session_persona(session_id, payload, user)


@app.post("/api/sessions/{session_id}/persona", response_model=LearningSessionPublic)
def post_session_persona(
    session_id: str,
    payload: PersonaRequest,
    user: UserPublic = Depends(require_user),
) -> LearningSessionPublic:
    session_id = require_resource_id(session_id, "会话")
    return save_session_persona(session_id, payload, user)


def save_session_persona(session_id: str, payload: PersonaRequest, user: UserPublic) -> LearningSessionPublic:
    session_id = require_resource_id(session_id, "会话")
    session = require_session(session_id, user)
    session.persona = payload.persona
    session.updated_at = datetime.now(UTC)
    store.save_session(session)
    return public_session_for_user(session, user)


@app.patch("/api/sessions/{session_id}/tutor-settings", response_model=LearningSessionPublic)
def update_session_tutor_settings(
    session_id: str,
    payload: TutorSettingsRequest,
    user: UserPublic = Depends(require_user),
) -> LearningSessionPublic:
    session_id = require_resource_id(session_id, "会话")
    session = require_session(session_id, user)
    session.tutor_settings = TutorSettings.model_validate(payload.model_dump())
    session.updated_at = datetime.now(UTC)
    store.save_session(session)
    return public_session_for_user(session, user)


@app.post("/api/sessions/{session_id}/chat", response_model=ChatResponse)
def chat_with_mentor(
    session_id: str,
    payload: ChatRequest,
    user: UserPublic = Depends(require_user),
) -> ChatResponse:
    session_id = require_resource_id(session_id, "会话")
    enforce_rate_limit(f"chat:{user.id}", CHAT_RATE_LIMIT)
    session = require_session(session_id, user)
    log_debug_event(
        "v1.chat.request",
        user_id=user.id,
        session_id=session_id,
        node_id=payload.node_id,
        persona=payload.persona,
        failure_count=payload.failure_count,
        preserve_persona=payload.preserve_persona,
        confusion_event=payload.confusion_event,
        starter_event=payload.starter_event,
        message=payload.message,
    )
    try:
        result = chat(
            session=session,
            node_id=payload.node_id,
            persona=payload.persona,
            message=payload.message,
            failure_count=payload.failure_count,
            preserve_persona=payload.preserve_persona,
            confusion_event=payload.confusion_event,
            starter_event=payload.starter_event,
            ai_config=active_api_config_for_chat(),
        )
    except ValueError as exc:
        log_debug_event("v1.chat.error", session_id=session_id, error=str(exc))
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except AiChatError as exc:
        log_debug_event("v1.chat.error", session_id=session_id, error=str(exc))
        raise HTTPException(status_code=502, detail=redact_secret_text(str(exc))) from exc
    store.save_session(result.session)
    log_debug_event(
        "v1.chat.response",
        session_id=session_id,
        node_id=payload.node_id,
        failure_count=result.failure_count,
        downgraded=result.downgraded,
        source=result.source,
        provider=result.provider,
        model=result.model,
        messages=[message.model_dump(mode="json") for message in messages_for_node(result.session, payload.node_id)],
        node_profile=result.session.node_profiles.get(payload.node_id),
    )
    return ChatResponse(
        messages=messages_for_node(result.session, payload.node_id),
        failure_count=result.failure_count,
        downgraded=result.downgraded,
        node_profiles=result.session.node_profiles,
        chat_source=result.source,
        chat_provider=result.provider if user.role == "admin" else None,
        chat_model=result.model if user.role == "admin" else None,
        chat_message=result.message,
    )


@app.post("/api/sessions/{session_id}/chat/stream")
def stream_chat_with_mentor(
    session_id: str,
    payload: ChatRequest,
    user: UserPublic = Depends(require_user),
) -> StreamingResponse:
    session_id = require_resource_id(session_id, "会话")
    enforce_rate_limit(f"chat-stream:{user.id}", CHAT_RATE_LIMIT)
    session = require_session(session_id, user)
    log_debug_event(
        "v1.chat.stream.request",
        user_id=user.id,
        session_id=session_id,
        node_id=payload.node_id,
        persona=payload.persona,
        failure_count=payload.failure_count,
        preserve_persona=payload.preserve_persona,
        confusion_event=payload.confusion_event,
        starter_event=payload.starter_event,
        message=payload.message,
    )

    def event_stream():
        try:
            for event in stream_chat_events(
                session=session,
                node_id=payload.node_id,
                persona=payload.persona,
                message=payload.message,
                failure_count=payload.failure_count,
                preserve_persona=payload.preserve_persona,
                confusion_event=payload.confusion_event,
                starter_event=payload.starter_event,
                ai_config=active_api_config_for_chat(),
            ):
                log_debug_event("v1.chat.stream.event", session_id=session_id, stream_event=event)
                if event["type"] == "done":
                    store.save_session(session)
                    event = {**event, "messages": [message.model_dump(mode="json") for message in messages_for_node(session, payload.node_id)]}
                    log_debug_event("v1.chat.stream.saved", session_id=session_id, stream_event=event)
                yield json.dumps(event, ensure_ascii=False) + "\n"
        except (ValueError, AiChatError) as exc:
            log_debug_event("v1.chat.stream.error", session_id=session_id, error=str(exc))
            yield json.dumps({"type": "error", "error": redact_secret_text(str(exc))}, ensure_ascii=False) + "\n"

    return StreamingResponse(event_stream(), media_type="application/x-ndjson")


@app.post("/api/sessions/{session_id}/feynman", response_model=FeynmanResponse)
def submit_feynman(
    session_id: str,
    payload: FeynmanRequest,
    user: UserPublic = Depends(require_user),
) -> FeynmanResponse:
    session_id = require_resource_id(session_id, "会话")
    enforce_rate_limit(f"feynman:{user.id}", FEYNMAN_RATE_LIMIT)
    session = require_session(session_id, user)
    log_debug_event(
        "feynman.submit.request",
        user_id=user.id,
        session_id=session_id,
        node_id=payload.node_id,
        explanation=payload.explanation,
        answers=[answer.model_dump(mode="json") for answer in payload.answers],
    )
    try:
        response = evaluate_feynman(
            session,
            payload.node_id,
            payload.explanation,
            payload.answers,
            active_api_config_for_feynman(),
        )
    except ValueError as exc:
        log_debug_event("feynman.submit.error", session_id=session_id, error=str(exc))
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except AiChatError as exc:
        log_debug_event("feynman.submit.error", session_id=session_id, error=str(exc))
        raise HTTPException(status_code=502, detail=redact_secret_text(str(exc))) from exc
    store.save_session(session)
    log_debug_event("feynman.submit.response", session_id=session_id, response=response.model_dump(mode="json"))
    return response


@app.post("/api/sessions/{session_id}/feynman/questions", response_model=FeynmanQuestionResponse)
def create_feynman_questions(
    session_id: str,
    payload: NodeSelectRequest,
    user: UserPublic = Depends(require_user),
) -> FeynmanQuestionResponse:
    session_id = require_resource_id(session_id, "会话")
    session = require_session(session_id, user)
    log_debug_event("feynman.questions.request", user_id=user.id, session_id=session_id, node_id=payload.node_id)
    try:
        node = find_node(session.nodes, payload.node_id)
        had_cached_questions = bool(session.feynman_questions.get(node.id, []))
        if had_cached_questions:
            log_debug_event("feynman.questions.reused", session_id=session_id, node_id=node.id)
            return FeynmanQuestionResponse(
                questions=session.feynman_questions.get(node.id, []),
                answers=session.feynman_answers.get(node.id, {}),
                reused=True,
            )
        enforce_rate_limit(f"feynman-questions:{user.id}", FEYNMAN_RATE_LIMIT)
        questions = generate_feynman_questions(session, payload.node_id, active_api_config_for_feynman())
    except ValueError as exc:
        log_debug_event("feynman.questions.error", session_id=session_id, error=str(exc))
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except AiChatError as exc:
        log_debug_event("feynman.questions.error", session_id=session_id, error=str(exc))
        raise HTTPException(status_code=502, detail=redact_secret_text(str(exc))) from exc
    store.save_session(session)
    log_debug_event(
        "feynman.questions.response",
        session_id=session_id,
        node_id=node.id,
        questions=[question.model_dump(mode="json") for question in questions],
        answers=session.feynman_answers.get(node.id, {}),
    )
    return FeynmanQuestionResponse(
        questions=questions,
        answers=session.feynman_answers.get(node.id, {}),
        reused=had_cached_questions,
    )


@app.post("/api/sessions/{session_id}/feynman/follow-up", response_model=FeynmanFollowUpResponse)
def create_feynman_follow_up(
    session_id: str,
    payload: FeynmanFollowUpRequest,
    user: UserPublic = Depends(require_user),
) -> FeynmanFollowUpResponse:
    session_id = require_resource_id(session_id, "会话")
    session = require_session(session_id, user)
    log_debug_event(
        "feynman.followup.request",
        user_id=user.id,
        session_id=session_id,
        node_id=payload.node_id,
        answer=payload.answer.model_dump(mode="json"),
    )
    try:
        node = find_node(session.nodes, payload.node_id)
    except ValueError as exc:
        log_debug_event("feynman.followup.error", session_id=session_id, error=str(exc))
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    questions = session.feynman_questions.get(node.id, [])
    cached_follow_up = session.feynman_followups.get(node.id, {}).get(payload.answer.question_id)
    if cached_follow_up is not None:
        save_feynman_answer(session, node.id, payload.answer)
        store.save_session(session)
        question = next((item for item in questions if item.id == cached_follow_up.question_id), None)
        log_debug_event("feynman.followup.reused_cached_state", session_id=session_id, followup=cached_follow_up.model_dump(mode="json"))
        return FeynmanFollowUpResponse(
            needed=cached_follow_up.needed,
            reason=cached_follow_up.reason,
            question=question,
            questions=session.feynman_questions.get(node.id, []),
            answers=session.feynman_answers.get(node.id, {}),
        )
    existing_follow_up = next(
        (
            question
            for question in questions
            if question.follow_up_of == payload.answer.question_id
        ),
        None,
    )
    if existing_follow_up is not None:
        save_feynman_answer(session, node.id, payload.answer)
        store.save_session(session)
        log_debug_event("feynman.followup.reused_existing_question", session_id=session_id, question=existing_follow_up.model_dump(mode="json"))
        return FeynmanFollowUpResponse(
            needed=True,
            reason="已存在针对该回答的追问，继续使用已保存的问题。",
            question=existing_follow_up,
            questions=session.feynman_questions.get(node.id, []),
            answers=session.feynman_answers.get(node.id, {}),
        )
    try:
        enforce_rate_limit(f"feynman-follow-up:{user.id}", FEYNMAN_RATE_LIMIT)
        response = generate_feynman_follow_up(session, payload.node_id, payload.answer, active_api_config_for_feynman())
    except ValueError as exc:
        log_debug_event("feynman.followup.error", session_id=session_id, error=str(exc))
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except AiChatError as exc:
        log_debug_event("feynman.followup.error", session_id=session_id, error=str(exc))
        raise HTTPException(status_code=502, detail=redact_secret_text(str(exc))) from exc
    store.save_session(session)
    log_debug_event("feynman.followup.response", session_id=session_id, response=response.model_dump(mode="json"))
    return response


@app.post("/api/sessions/{session_id}/feynman/answer", response_model=FeynmanAnswerSaveResponse)
def save_feynman_answer_progress(
    session_id: str,
    payload: FeynmanAnswerSaveRequest,
    user: UserPublic = Depends(require_user),
) -> FeynmanAnswerSaveResponse:
    session_id = require_resource_id(session_id, "会话")
    session = require_session(session_id, user)
    try:
        node = find_node(session.nodes, payload.node_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    save_feynman_answer(session, node.id, payload.answer)
    session.updated_at = datetime.now(UTC)
    store.save_session(session)
    return FeynmanAnswerSaveResponse(
        questions=session.feynman_questions.get(node.id, []),
        answers=session.feynman_answers.get(node.id, {}),
    )


@app.get("/api/admin/users", response_model=list[UserPublic])
def admin_list_users(
    _: UserPublic = Depends(require_recent_admin_reauth),
    limit: int = Query(default=200, ge=1, le=500),
) -> list[UserPublic]:
    return store.list_users(limit)


@app.patch("/api/admin/users/{user_id}", response_model=UserPublic)
def admin_update_user(
    user_id: str,
    payload: UserUpdateRequest,
    admin: UserPublic = Depends(require_recent_admin_reauth),
) -> UserPublic:
    user_id = require_resource_id(user_id, "用户")
    enforce_admin_write_limit(admin, "users")
    current = store.get_user_by_id(user_id)
    if current is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    if would_remove_last_admin(user_id, payload):
        raise HTTPException(status_code=400, detail="不能降级或禁用最后一个管理员")
    user = store.update_user(
        user_id=user_id,
        role=payload.role,
        is_active=payload.is_active,
        updated_at=now_iso(),
    )
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    role_changed = payload.role is not None and payload.role != current.role
    deactivated = payload.is_active is False and current.is_active
    revoked_tokens = store.delete_user_tokens(user_id) if role_changed or deactivated else 0
    audit_event(
        admin,
        "admin.user.update",
        "user",
        user_id,
        {"role": payload.role, "is_active": payload.is_active, "revoked_tokens": revoked_tokens},
    )
    return user


def would_remove_last_admin(user_id: str, payload: UserUpdateRequest) -> bool:
    users = store.list_users()
    target = next((user for user in users if user.id == user_id), None)
    if target is None or target.role != "admin" or not target.is_active:
        return False

    next_role = payload.role if payload.role is not None else target.role
    next_active = target.is_active if payload.is_active is None else payload.is_active
    if next_role == "admin" and next_active:
        return False

    active_admins = [user for user in users if user.role == "admin" and user.is_active]
    return len(active_admins) <= 1


@app.get("/api/admin/api-configs", response_model=list[ApiConfig])
def admin_list_api_configs(
    _: UserPublic = Depends(require_admin),
    limit: int = Query(default=100, ge=1, le=200),
) -> list[ApiConfig]:
    return store.list_api_configs(limit)


@app.get("/api/admin/audit-logs", response_model=list[AuditLogEntry])
def admin_list_audit_logs(
    _: UserPublic = Depends(require_recent_admin_reauth),
    limit: int = Query(default=200, ge=1, le=500),
) -> list[AuditLogEntry]:
    return store.list_audit_logs(limit)


@app.get("/api/admin/research-dashboard", response_model=ResearchDashboardResponse)
def admin_research_dashboard(
    _: UserPublic = Depends(require_admin),
) -> ResearchDashboardResponse:
    return store.research_dashboard()


@app.post("/api/admin/research-experiments", response_model=ResearchExperimentImportResponse)
def admin_import_research_experiments(
    payload: ResearchExperimentImportRequest,
    admin: UserPublic = Depends(require_recent_admin_reauth),
) -> ResearchExperimentImportResponse:
    enforce_admin_write_limit(admin, "research-experiments")
    timestamp = now_iso()
    records = store.import_research_experiment_records(
        records=payload.records,
        imported_at=timestamp,
        id_factory=lambda: uuid4().hex,
    )
    audit_event(
        admin,
        "admin.research_experiment.import",
        "research_experiment",
        None,
        {"imported_count": len(records), "studies": sorted({record.study_id for record in records})[:20]},
    )
    return ResearchExperimentImportResponse(imported_count=len(records), records=records)


@app.get("/api/admin/research-experiments/export", response_model=ResearchExperimentExportResponse)
def admin_export_research_experiments(
    _: UserPublic = Depends(require_admin),
) -> ResearchExperimentExportResponse:
    return ResearchExperimentExportResponse(
        generated_at=datetime.now(UTC),
        records=store.list_research_experiment_records(limit=2000),
    )


@app.get("/api/admin/research-blind-review/export", response_model=ResearchBlindReviewExportResponse)
def admin_export_blind_review_answers(
    _: UserPublic = Depends(require_admin),
) -> ResearchBlindReviewExportResponse:
    return ResearchBlindReviewExportResponse(
        generated_at=datetime.now(UTC),
        answers=store.export_blind_review_answers(limit=2000),
    )


@app.post("/api/admin/api-configs", response_model=ApiConfig)
def admin_create_api_config(
    payload: ApiConfigCreateRequest,
    admin: UserPublic = Depends(require_recent_admin_reauth),
) -> ApiConfig:
    enforce_admin_write_limit(admin, "api-configs")
    timestamp = now_iso()
    log_debug_event(
        "admin.api_config.create.request",
        admin_user_id=admin.id,
        provider=payload.provider,
        base_url=payload.base_url,
        model=payload.model,
        is_active=payload.is_active,
        api_key_provided=bool(payload.api_key),
    )
    try:
        config = store.upsert_api_config(
            config_id=uuid4().hex,
            provider=payload.provider,
            base_url=payload.base_url,
            api_key=payload.api_key,
            model=payload.model,
            is_active=payload.is_active,
            created_at=timestamp,
            updated_at=timestamp,
        )
        audit_event(admin, "admin.api_config.create", "api_config", config.id, safe_api_config_detail(config))
        log_debug_event("admin.api_config.create.response", admin_user_id=admin.id, config=safe_api_config_detail(config))
        return config
    except ValueError as exc:
        log_debug_event("admin.api_config.create.error", admin_user_id=admin.id, error=str(exc))
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.patch("/api/admin/api-configs/{config_id}", response_model=ApiConfig)
def admin_update_api_config(
    config_id: str,
    payload: ApiConfigUpdateRequest,
    admin: UserPublic = Depends(require_recent_admin_reauth),
) -> ApiConfig:
    config_id = require_resource_id(config_id, "API 配置")
    enforce_admin_write_limit(admin, "api-configs")
    current = store.get_api_config(config_id)
    if current is None:
        raise HTTPException(status_code=404, detail="API 配置不存在")
    current_secret = store.get_api_config_secret(config_id) or ""
    timestamp = now_iso()
    log_debug_event(
        "admin.api_config.update.request",
        admin_user_id=admin.id,
        config_id=config_id,
        provider=payload.provider,
        base_url=payload.base_url,
        model=payload.model,
        is_active=payload.is_active,
        api_key_provided=payload.api_key is not None,
    )
    try:
        config = store.upsert_api_config(
            config_id=config_id,
            provider=payload.provider or current.provider,
            base_url=payload.base_url or current.base_url,
            api_key=current_secret if payload.api_key is None else payload.api_key,
            model=current.model if payload.model is None else payload.model,
            is_active=current.is_active if payload.is_active is None else payload.is_active,
            created_at=current.created_at.isoformat(),
            updated_at=timestamp,
        )
        audit_event(admin, "admin.api_config.update", "api_config", config.id, safe_api_config_detail(config))
        log_debug_event("admin.api_config.update.response", admin_user_id=admin.id, config=safe_api_config_detail(config))
        return config
    except ValueError as exc:
        log_debug_event("admin.api_config.update.error", admin_user_id=admin.id, config_id=config_id, error=str(exc))
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.delete("/api/admin/api-configs/{config_id}")
def admin_delete_api_config(
    config_id: str,
    admin: UserPublic = Depends(require_recent_admin_reauth),
) -> dict[str, bool]:
    config_id = require_resource_id(config_id, "API 配置")
    enforce_admin_write_limit(admin, "api-configs")
    if not store.delete_api_config(config_id):
        raise HTTPException(status_code=404, detail="API 配置不存在")
    audit_event(admin, "admin.api_config.delete", "api_config", config_id)
    log_debug_event("admin.api_config.delete", admin_user_id=admin.id, config_id=config_id)
    return {"ok": True}


def audit_event(
    actor: UserPublic | None,
    action: str,
    target_type: str,
    target_id: str | None,
    detail: dict[str, object] | None = None,
) -> None:
    store.create_audit_log(
        log_id=uuid4().hex,
        actor_user_id=actor.id if actor else None,
        actor_username=actor.username if actor else None,
        action=action,
        target_type=target_type,
        target_id=target_id,
        detail=json.dumps(detail or {}, ensure_ascii=False, sort_keys=True),
        created_at=now_iso(),
    )


def safe_api_config_detail(config: ApiConfig) -> dict[str, object]:
    return {
        "provider": config.provider,
        "base_url": config.base_url,
        "model": config.model,
        "is_active": config.is_active,
    }


def require_session(session_id: str, user: UserPublic) -> LearningSession:
    session = store.get_session(session_id, None if user.role == "admin" else user.id)
    if session is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    return session


def run_parse_job(job_id: str) -> None:
    log_debug_event("parse.job.worker.start", job_id=job_id)
    if not PARSE_JOB_SEMAPHORE.acquire(blocking=False):
        log_debug_event("parse.job.worker.busy", job_id=job_id)
        store.update_parse_job(
            job_id,
            "failed",
            100,
            "解析服务繁忙，请稍后重试。",
            now_iso(),
            session_id=None,
            error="解析服务繁忙，请稍后重试。",
        )
        store.clear_parse_job_content(job_id)
        return
    payload = store.get_parse_job_content(job_id)
    try:
        if payload is None:
            log_debug_event("parse.job.worker.missing_payload", job_id=job_id)
            return
        user_id, title, content = payload
        log_debug_event(
            "parse.job.worker.payload",
            job_id=job_id,
            user_id=user_id,
            title=title,
            content_chars=len(content),
            content_preview=sanitize_debug_text(content, limit=1600),
        )
        store.update_parse_job(job_id, "running", 12, "正在读取材料文本", now_iso())
        log_debug_event("parse.job.progress", job_id=job_id, status="running", progress=12, message="正在读取材料文本")
        store.update_parse_job(job_id, "running", 28, "正在清洗材料结构", now_iso())
        log_debug_event("parse.job.progress", job_id=job_id, status="running", progress=28, message="正在清洗材料结构")
        ai_config = active_api_config_or_error()
        log_debug_event(
            "parse.job.ai_config",
            job_id=job_id,
            provider=ai_config.get("provider"),
            base_url=ai_config.get("base_url"),
            model=ai_config.get("model"),
        )
        store.update_parse_job(job_id, "running", 42, "正在提取关键概念", now_iso())
        log_debug_event("parse.job.progress", job_id=job_id, status="running", progress=42, message="正在提取关键概念")
        store.update_parse_job(job_id, "running", 58, "正在生成知识节点", now_iso())
        log_debug_event("parse.job.progress", job_id=job_id, status="running", progress=58, message="正在生成知识节点")
        heartbeat_stop = Event()
        heartbeat = Thread(target=parse_job_model_heartbeat, args=(job_id, heartbeat_stop), daemon=True)
        heartbeat.start()
        try:
            session = create_session(title, content, user_id, ai_config)
        finally:
            heartbeat_stop.set()
            heartbeat.join(timeout=1)
        log_debug_event(
            "parse.job.session.generated",
            job_id=job_id,
            session_id=session.id,
            node_count=len(session.nodes),
            nodes=[node.model_dump(mode="json") for node in session.nodes],
            parse_source=session.parse_source,
            parse_provider=session.parse_provider,
            parse_model=session.parse_model,
        )
        store.update_parse_job(job_id, "running", 78, "正在计算节点依赖关系", now_iso())
        log_debug_event("parse.job.progress", job_id=job_id, status="running", progress=78, message="正在计算节点依赖关系")
        store.update_parse_job(job_id, "running", 84, "正在写入 GraphRAG 知识底座", now_iso())
        log_debug_event("parse.job.progress", job_id=job_id, status="running", progress=84, message="正在写入 GraphRAG 知识底座")
        graph_message = index_session_graphrag(session, content, ai_config)
        session.parse_message = f"{session.parse_message}；{graph_message}"
        store.update_parse_job(job_id, "running", 88, "GraphRAG 处理完成", now_iso())
        log_debug_event("parse.job.progress", job_id=job_id, status="running", progress=88, message=graph_message)
        store.update_parse_job(job_id, "running", 92, "正在提前准备导师首句和讲台问题", now_iso())
        log_debug_event("parse.job.progress", job_id=job_id, status="running", progress=92, message="正在提前准备导师首句和讲台问题")
        prewarm_stats = prewarm_learning_assets(session, ai_config)
        session.parse_message = (
            f"{session.parse_message}；已预生成 {prewarm_stats['starters']} 个导师首句、"
            f"{prewarm_stats['questions']} 组费曼问题"
        )
        if prewarm_stats["errors"]:
            session.parse_message = f"{session.parse_message}（{prewarm_stats['errors']} 个节点预热失败，进入时自动补齐）"
        log_debug_event("parse.job.prewarm.completed", job_id=job_id, session_id=session.id, stats=prewarm_stats)
        store.update_parse_job(job_id, "running", 96, "正在保存学习记录", now_iso())
        log_debug_event("parse.job.progress", job_id=job_id, status="running", progress=96, message="正在保存学习记录")
        store.save_session(session)
        if store.get_session(session.id, user_id) is None:
            raise RuntimeError("学习记录保存失败，请重新解析。")
        store.update_parse_job(
            job_id,
            "completed",
            100,
            session.parse_message,
            now_iso(),
            session_id=session.id,
            error=None,
        )
        log_debug_event(
            "parse.job.completed",
            job_id=job_id,
            session_id=session.id,
            progress=100,
            message=session.parse_message,
        )
    except (AiSplitError, Exception) as exc:
        log_debug_event("parse.job.failed", job_id=job_id, error=str(exc))
        store.update_parse_job(
            job_id,
            "failed",
            100,
            "解析失败",
            now_iso(),
            session_id=None,
            error=redact_secret_text(str(exc)),
        )
    finally:
        PARSE_JOB_SEMAPHORE.release()
        store.clear_parse_job_content(job_id)
        log_debug_event("parse.job.worker.finish", job_id=job_id)


def parse_job_model_heartbeat(job_id: str, stop_event: Event) -> None:
    progress_steps = [60, 62, 64, 66, 68, 70, 72, 74]
    for progress in progress_steps:
        if stop_event.wait(3):
            return
        current = store.get_parse_job(job_id)
        if current is None or current.status != "running":
            return
        if current.progress >= 78:
            return
        store.update_parse_job(job_id, "running", progress, "模型正在拆分关键知识点", now_iso())
        log_debug_event("parse.job.progress", job_id=job_id, status="running", progress=progress, message="模型正在拆分关键知识点")


def reset_parse_job_semaphore_for_tests() -> None:
    global PARSE_JOB_SEMAPHORE
    PARSE_JOB_SEMAPHORE = BoundedSemaphore(max_concurrent_parse_jobs())


# 挂载 V2 多智能体主路线；V1 接口仅保留为过时回退。
# 需要放在认证依赖定义之后，避免 V2 子模块导入 require_user 时出现循环初始化。
from .v2.router import v2_router

app.include_router(v2_router)
