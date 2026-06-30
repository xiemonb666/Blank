from __future__ import annotations

import json
import os
import re
import uuid
import urllib.error
import urllib.request
from dataclasses import dataclass
from collections.abc import Callable
from urllib.parse import urljoin

from .debug_logging import log_debug_event
from .models import SpeechCapabilitiesResponse, SpeechTranscriptionResponse
from .security import redact_secret_text, validate_model_request_parts
from .services import open_model_request, read_model_response


MAX_SPEECH_UPLOAD_BYTES = 15 * 1024 * 1024
MAX_TTS_AUDIO_BYTES = 24 * 1024 * 1024
DEFAULT_SPEECH_TIMEOUT_SECONDS = 90
ALLOWED_AUDIO_CONTENT_TYPES = {
    "application/octet-stream",
    "audio/mp4",
    "audio/mpeg",
    "audio/ogg",
    "audio/wav",
    "audio/webm",
    "video/mp4",
    "video/webm",
}


class SpeechServiceError(RuntimeError):
    pass


@dataclass(frozen=True)
class SpeechEndpointConfig:
    provider: str
    base_url: str
    api_key: str
    model: str
    path: str
    voice: str | None = None
    language: str | None = None
    response_format: str | None = None


@dataclass(frozen=True)
class SpeechSynthesisResult:
    audio: bytes
    content_type: str
    provider: str
    voice: str | None


_SPEECH_CONFIG_PROVIDER: Callable[[str], dict[str, str] | None] | None = None


def set_speech_config_provider(provider: Callable[[str], dict[str, str] | None] | None) -> None:
    global _SPEECH_CONFIG_PROVIDER
    _SPEECH_CONFIG_PROVIDER = provider


def speech_capabilities() -> SpeechCapabilitiesResponse:
    asr = optional_asr_config()
    tts = optional_tts_config()
    return SpeechCapabilitiesResponse(
        asr_enabled=asr is not None,
        tts_enabled=tts is not None,
        asr_provider=asr.provider if asr else None,
        asr_model=asr.model if asr else None,
        tts_provider=tts.provider if tts else None,
        tts_voice=default_tts_voice(tts) if tts else None,
    )


def transcribe_audio(
    audio_bytes: bytes,
    filename: str,
    content_type: str,
    language: str | None = None,
    prompt: str | None = None,
) -> SpeechTranscriptionResponse:
    if not audio_bytes:
        raise SpeechServiceError("音频内容为空，无法转写。")
    if len(audio_bytes) > MAX_SPEECH_UPLOAD_BYTES:
        raise SpeechServiceError("音频过大，请控制在 15MB 以内。")
    normalized_content_type = normalize_audio_content_type(content_type)
    config = require_asr_config()
    boundary = f"blank-speech-{uuid.uuid4().hex}"
    payload = build_multipart_body(
        boundary,
        fields={
            "model": config.model,
            "language": normalize_optional_text(language, 24),
            "prompt": normalize_optional_text(prompt, 400),
            "response_format": "json",
        },
        files=[
            {
                "name": "file",
                "filename": safe_audio_filename(filename, normalized_content_type),
                "content_type": normalized_content_type,
                "content": audio_bytes,
            }
        ],
    )
    request = urllib.request.Request(
        speech_endpoint_url(config),
        data=payload,
        method="POST",
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Accept": "application/json",
            **authorization_header(config.api_key),
        },
    )
    try:
        with open_model_request(request, timeout=speech_request_timeout()) as response:
            raw = read_model_response(response)
            response_type = response.headers.get("content-type", "application/json")
    except urllib.error.HTTPError as exc:
        raise SpeechServiceError(
            f"ASR 服务返回 HTTP {exc.code}：{safe_speech_http_error_detail(exc)}"
        ) from exc
    except urllib.error.URLError as exc:
        raise SpeechServiceError(f"ASR 服务不可用：{redact_secret_text(str(exc.reason), limit=180)}") from exc
    except ValueError as exc:
        raise SpeechServiceError(redact_secret_text(str(exc), limit=180)) from exc

    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SpeechServiceError(f"ASR 返回内容无法解析：{redact_secret_text(response_type, limit=120)}") from exc
    text = extract_transcript_text(payload)
    if not text:
        raise SpeechServiceError("ASR 没有返回可用文本，请检查 SenseVoice 服务配置。")
    log_debug_event(
        "speech.asr.transcribed",
        provider=config.provider,
        model=config.model,
        content_type=normalized_content_type,
        chars=len(text),
    )
    return SpeechTranscriptionResponse(text=text, provider=config.provider, model=config.model)


def synthesize_speech(text: str, voice: str | None = None, language: str | None = None) -> SpeechSynthesisResult:
    normalized_text = normalize_required_text(text, 4000, "TTS 文本")
    config = require_tts_config()
    payload = json.dumps(
        {
            "model": config.model,
            "input": normalized_text,
            "voice": normalize_optional_text(voice, 80) or default_tts_voice(config),
            "response_format": default_tts_format(config),
            "language": normalize_optional_text(language, 24) or default_tts_language(config),
        },
        ensure_ascii=False,
    ).encode("utf-8")
    request = urllib.request.Request(
        speech_endpoint_url(config),
        data=payload,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": f"{tts_accept_header(config)}, application/json",
            **authorization_header(config.api_key),
        },
    )
    try:
        with open_model_request(request, timeout=speech_request_timeout()) as response:
            raw = read_model_response(response, limit=MAX_TTS_AUDIO_BYTES)
            response_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    except urllib.error.HTTPError as exc:
        raise SpeechServiceError(
            f"TTS 服务返回 HTTP {exc.code}：{safe_speech_http_error_detail(exc)}"
        ) from exc
    except urllib.error.URLError as exc:
        raise SpeechServiceError(f"TTS 服务不可用：{redact_secret_text(str(exc.reason), limit=180)}") from exc
    except ValueError as exc:
        raise SpeechServiceError(redact_secret_text(str(exc), limit=180)) from exc

    audio, content_type = parse_tts_response(raw, response_type or default_tts_mime_type(config))
    log_debug_event(
        "speech.tts.synthesized",
        provider=config.provider,
        model=config.model,
        voice=normalize_optional_text(voice, 80) or default_tts_voice(config),
        chars=len(normalized_text),
        bytes=len(audio),
        content_type=content_type,
    )
    return SpeechSynthesisResult(
        audio=audio,
        content_type=content_type,
        provider=config.provider,
        voice=normalize_optional_text(voice, 80) or default_tts_voice(config),
    )


def optional_asr_config() -> SpeechEndpointConfig | None:
    configured = configured_speech_endpoint("asr")
    if configured is not None:
        return configured
    base_url = os.getenv("BLANK_ASR_BASE_URL", "").strip()
    if not base_url:
        return None
    provider = os.getenv("BLANK_ASR_PROVIDER", "sensevoice-openai").strip().lower() or "sensevoice-openai"
    path = os.getenv("BLANK_ASR_TRANSCRIBE_PATH", "/v1/audio/transcriptions").strip() or "/v1/audio/transcriptions"
    model = os.getenv("BLANK_ASR_MODEL", "SenseVoiceSmall").strip() or "SenseVoiceSmall"
    api_key = os.getenv("BLANK_ASR_API_KEY", "blank-local-asr").strip() or "blank-local-asr"
    normalized_base_url, normalized_api_key, normalized_model = validate_model_request_parts(base_url, api_key, model)
    return SpeechEndpointConfig(
        provider=provider,
        base_url=normalized_base_url,
        api_key=normalized_api_key,
        model=normalized_model,
        path=normalize_endpoint_path(path),
    )


def optional_tts_config() -> SpeechEndpointConfig | None:
    configured = configured_speech_endpoint("tts")
    if configured is not None:
        return configured
    base_url = os.getenv("BLANK_TTS_BASE_URL", "").strip()
    if not base_url:
        return None
    provider = os.getenv("BLANK_TTS_PROVIDER", "supertonic-http").strip().lower() or "supertonic-http"
    path = os.getenv("BLANK_TTS_PATH", "/v1/audio/speech").strip() or "/v1/audio/speech"
    model = os.getenv("BLANK_TTS_MODEL", "supertonic").strip() or "supertonic"
    api_key = os.getenv("BLANK_TTS_API_KEY", "blank-local-tts").strip() or "blank-local-tts"
    normalized_base_url, normalized_api_key, normalized_model = validate_model_request_parts(base_url, api_key, model)
    return SpeechEndpointConfig(
        provider=provider,
        base_url=normalized_base_url,
        api_key=normalized_api_key,
        model=normalized_model,
        path=normalize_endpoint_path(path),
        voice=default_tts_voice(),
        language=default_tts_language(),
        response_format=default_tts_format(),
    )


def require_asr_config() -> SpeechEndpointConfig:
    config = optional_asr_config()
    if config is None:
        raise SpeechServiceError("尚未配置 ASR 服务，请先设置 SenseVoice 接口环境变量。")
    return config


def require_tts_config() -> SpeechEndpointConfig:
    config = optional_tts_config()
    if config is None:
        raise SpeechServiceError("尚未配置 TTS 服务，请先设置 Supertonic 接口环境变量。")
    return config


def normalize_audio_content_type(content_type: str) -> str:
    normalized = content_type.split(";", 1)[0].strip().lower()
    if not normalized:
        return "audio/webm"
    if normalized.startswith("audio/") or normalized in ALLOWED_AUDIO_CONTENT_TYPES:
        return normalized
    raise SpeechServiceError("仅支持常见音频格式上传。")


def safe_audio_filename(filename: str, content_type: str) -> str:
    extension = audio_extension_for(content_type)
    raw = os.path.basename(filename or "").strip().replace("\x00", "")
    if not raw:
        return f"recording{extension}"
    stem, ext = os.path.splitext(raw[:120])
    safe_stem = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("._-")
    safe_ext = re.sub(r"[^A-Za-z0-9.]+", "", ext.lower())[:12]
    if not safe_ext:
        safe_ext = extension
    return f"{safe_stem or 'recording'}{safe_ext}"


def audio_extension_for(content_type: str) -> str:
    mapping = {
        "audio/mp4": ".m4a",
        "audio/mpeg": ".mp3",
        "audio/ogg": ".ogg",
        "audio/wav": ".wav",
        "audio/webm": ".webm",
        "video/mp4": ".mp4",
        "video/webm": ".webm",
    }
    return mapping.get(content_type, ".webm")


def normalize_endpoint_path(path: str) -> str:
    normalized = path.strip()
    if not normalized:
        return "/"
    return normalized if normalized.startswith("/") else f"/{normalized}"


def configured_speech_endpoint(kind: str) -> SpeechEndpointConfig | None:
    if _SPEECH_CONFIG_PROVIDER is None:
        return None
    try:
        record = _SPEECH_CONFIG_PROVIDER(kind)
    except Exception as exc:
        log_debug_event("speech.config.load_failed", kind=kind, error=redact_secret_text(str(exc), limit=180))
        return None
    if not record:
        return None
    base_url, api_key, model = validate_model_request_parts(
        str(record.get("base_url") or ""),
        str(record.get("api_key") or ""),
        str(record.get("model") or ""),
    )
    return SpeechEndpointConfig(
        provider=str(record.get("provider") or "").strip().lower(),
        base_url=base_url,
        api_key=api_key,
        model=model,
        path=normalize_endpoint_path(str(record.get("path") or default_speech_path(kind))),
        voice=normalize_optional_text(record.get("voice"), 80),
        language=normalize_optional_text(record.get("language"), 24),
        response_format=normalize_optional_text(record.get("response_format"), 16),
    )


def default_speech_path(kind: str) -> str:
    return "/v1/audio/transcriptions" if kind == "asr" else "/v1/audio/speech"


def default_tts_voice(config: SpeechEndpointConfig | None = None) -> str:
    if config and config.voice:
        return config.voice
    return normalize_optional_text(os.getenv("BLANK_TTS_VOICE", "F1"), 80) or "F1"


def default_tts_language(config: SpeechEndpointConfig | None = None) -> str:
    if config and config.language:
        return config.language
    return normalize_optional_text(os.getenv("BLANK_TTS_LANGUAGE", "zh"), 24) or "zh"


def default_tts_format(config: SpeechEndpointConfig | None = None) -> str:
    value = (config.response_format if config and config.response_format else None) or normalize_optional_text(
        os.getenv("BLANK_TTS_RESPONSE_FORMAT", "wav"),
        16,
    ) or "wav"
    return value.lower()


def default_tts_mime_type(config: SpeechEndpointConfig | None = None) -> str:
    mapping = {
        "mp3": "audio/mpeg",
        "opus": "audio/ogg",
        "wav": "audio/wav",
    }
    return mapping.get(default_tts_format(config), "audio/wav")


def tts_accept_header(config: SpeechEndpointConfig | None = None) -> str:
    return default_tts_mime_type(config)


def speech_request_timeout() -> int:
    configured = os.getenv("BLANK_SPEECH_READ_TIMEOUT", "").strip()
    if not configured:
        return DEFAULT_SPEECH_TIMEOUT_SECONDS
    try:
        value = int(configured)
    except ValueError:
        return DEFAULT_SPEECH_TIMEOUT_SECONDS
    return max(10, min(value, 300))


def speech_endpoint_url(config: SpeechEndpointConfig) -> str:
    return urljoin(f"{config.base_url.rstrip('/')}/", config.path.lstrip("/"))


def authorization_header(api_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key}"} if api_key else {}


def normalize_required_text(value: str, limit: int, label: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise SpeechServiceError(f"{label}不能为空。")
    return normalized[:limit]


def normalize_optional_text(value: str | None, limit: int) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    return normalized[:limit]


def build_multipart_body(boundary: str, fields: dict[str, str | None], files: list[dict[str, object]]) -> bytes:
    chunks: list[bytes] = []
    boundary_bytes = boundary.encode("utf-8")
    for name, value in fields.items():
        if value is None or value == "":
            continue
        chunks.extend(
            [
                b"--" + boundary_bytes + b"\r\n",
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"),
                str(value).encode("utf-8"),
                b"\r\n",
            ]
        )
    for item in files:
        chunks.extend(
            [
                b"--" + boundary_bytes + b"\r\n",
                (
                    f'Content-Disposition: form-data; name="{item["name"]}"; '
                    f'filename="{item["filename"]}"\r\n'
                ).encode("utf-8"),
                f'Content-Type: {item["content_type"]}\r\n\r\n'.encode("utf-8"),
                bytes(item["content"]),
                b"\r\n",
            ]
        )
    chunks.append(b"--" + boundary_bytes + b"--\r\n")
    return b"".join(chunks)


def extract_transcript_text(payload: object) -> str:
    if isinstance(payload, dict):
        for key in ("text", "transcript"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        data = payload.get("data")
        if isinstance(data, dict):
            return extract_transcript_text(data)
        choices = payload.get("choices")
        if isinstance(choices, list):
            for item in choices:
                text = extract_transcript_text(item)
                if text:
                    return text
    return ""


def parse_tts_response(raw: bytes, response_type: str) -> tuple[bytes, str]:
    normalized_type = response_type.lower()
    if normalized_type.startswith("audio/"):
        if not raw:
            raise SpeechServiceError("TTS 没有返回音频数据。")
        return raw, normalized_type
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SpeechServiceError("TTS 返回内容无法解析。") from exc
    if isinstance(payload, dict):
        audio = payload.get("audio")
        if isinstance(audio, str) and audio:
            import base64

            try:
                return base64.b64decode(audio), str(payload.get("content_type") or default_tts_mime_type())
            except ValueError as exc:
                raise SpeechServiceError("TTS 返回了无法解码的音频数据。") from exc
        error_message = payload.get("error")
        if isinstance(error_message, str) and error_message.strip():
            raise SpeechServiceError(redact_secret_text(error_message, limit=180))
    raise SpeechServiceError("TTS 没有返回可播放音频。")


def safe_speech_http_error_detail(exc: urllib.error.HTTPError) -> str:
    try:
        raw = exc.read(2048).decode("utf-8", errors="replace")
    except Exception:
        raw = ""
    if not raw:
        return "服务未提供更多信息。"
    return redact_secret_text(raw, limit=180).replace("\n", " ")
