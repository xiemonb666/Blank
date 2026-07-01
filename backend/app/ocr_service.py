from __future__ import annotations

import base64
import json
import os
import secrets
import urllib.request
from typing import Any

from .security import redact_secret_text, validate_model_base_url, validate_speech_endpoint_path
from .services import open_model_request, read_model_response


DEFAULT_OCR_PATH = "/ocr"
MAX_OCR_RESPONSE_BYTES = 512 * 1024


class OcrServiceError(RuntimeError):
    pass


def ocr_enabled() -> bool:
    return os.getenv("BLANK_OCR_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}


def ocr_base_url() -> str:
    configured = (
        os.getenv("BLANK_UNLIMITED_OCR_BASE_URL", "").strip()
        or os.getenv("BLANK_OCR_BASE_URL", "").strip()
    )
    if not configured:
        raise OcrServiceError("未配置 Unlimited-OCR 服务地址，请设置 BLANK_UNLIMITED_OCR_BASE_URL。")
    try:
        return validate_model_base_url(configured)
    except ValueError as exc:
        raise OcrServiceError(f"OCR Base URL 不合法：{exc}") from exc


def ocr_path() -> str:
    try:
        return validate_speech_endpoint_path(os.getenv("BLANK_UNLIMITED_OCR_PATH", DEFAULT_OCR_PATH))
    except ValueError as exc:
        raise OcrServiceError(f"OCR 接口路径不合法：{exc}") from exc


def extract_image_text(filename: str | None, content_type: str | None, raw: bytes) -> str:
    if not ocr_enabled():
        raise OcrServiceError("图片材料需要启用 OCR：请配置 BLANK_OCR_ENABLED=true 和 Unlimited-OCR 服务地址。")
    endpoint = f"{ocr_base_url()}{ocr_path()}"
    try:
        payload = call_unlimited_ocr(endpoint, filename or "image", content_type or "application/octet-stream", raw)
        text = parse_ocr_text(payload)
    except OcrServiceError:
        raise
    except Exception as exc:
        safe_detail = redact_secret_text(str(exc), limit=180)
        raise OcrServiceError(f"Unlimited-OCR 调用失败：{safe_detail}") from exc
    if not text.strip():
        raise OcrServiceError("Unlimited-OCR 未返回可用文本。")
    return text.strip()


def call_unlimited_ocr(endpoint: str, filename: str, content_type: str, raw: bytes) -> dict[str, Any]:
    mode = os.getenv("BLANK_UNLIMITED_OCR_REQUEST_MODE", "multipart").strip().lower()
    if mode == "json":
        body = json.dumps({
            "filename": filename,
            "content_type": content_type,
            "image": base64.b64encode(raw).decode("ascii"),
        }).encode("utf-8")
        headers = {"Content-Type": "application/json"}
    else:
        boundary = f"----BlankOCR{secrets.token_hex(12)}"
        body = multipart_body(boundary, filename, content_type, raw)
        headers = {"Content-Type": f"multipart/form-data; boundary={boundary}"}
    request = urllib.request.Request(endpoint, data=body, headers=headers, method="POST")
    with open_model_request(request, timeout=float(os.getenv("BLANK_OCR_TIMEOUT_SECONDS", "60"))) as response:
        raw_body = read_model_response(response, limit=MAX_OCR_RESPONSE_BYTES).decode("utf-8", errors="replace")
    try:
        parsed = json.loads(raw_body)
    except json.JSONDecodeError as exc:
        raise OcrServiceError(f"OCR 返回不是合法 JSON：{raw_body[:120]}") from exc
    if not isinstance(parsed, dict):
        raise OcrServiceError("OCR 返回格式不是 JSON 对象。")
    return parsed


def multipart_body(boundary: str, filename: str, content_type: str, raw: bytes) -> bytes:
    safe_name = filename.replace('"', "_").replace("\r", "_").replace("\n", "_")
    head = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{safe_name}"\r\n'
        f"Content-Type: {content_type}\r\n\r\n"
    ).encode("utf-8")
    tail = f"\r\n--{boundary}--\r\n".encode("utf-8")
    return head + raw + tail


def parse_ocr_text(payload: dict[str, Any]) -> str:
    candidates = [
        payload.get("text"),
        payload.get("result"),
        payload.get("content"),
        payload.get("markdown"),
    ]
    data = payload.get("data")
    if isinstance(data, dict):
        candidates.extend([data.get("text"), data.get("result"), data.get("content"), data.get("markdown")])
    for candidate in candidates:
        if isinstance(candidate, str) and candidate.strip():
            return candidate
    blocks = payload.get("blocks") or (data.get("blocks") if isinstance(data, dict) else None)
    if isinstance(blocks, list):
        lines = []
        for item in blocks:
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                lines.append(item["text"].strip())
            elif isinstance(item, str):
                lines.append(item.strip())
        return "\n".join(line for line in lines if line)
    return ""
