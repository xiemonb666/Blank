from __future__ import annotations

import json
import logging
import os
import re
import sys
import time
from datetime import UTC, datetime
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import Any

from .security import redact_secret_text

BASE_DIR = Path(__file__).resolve().parents[1]
DEBUG_LOGGER_NAME = "blank.debug"
MAX_DEBUG_FIELD_CHARS = 20_000
MAX_DEBUG_JSON_CHARS = 80_000
SENSITIVE_KEYS = {
    "api_key",
    "apikey",
    "authorization",
    "cookie",
    "csrf",
    "password",
    "secret",
    "token",
    "x-csrf-token",
}
FALSE_VALUES = {"0", "false", "no", "off"}


class PeriodicSizeRotatingFileHandler(TimedRotatingFileHandler):
    """按固定时间轮转日志，同时在单文件过大时提前轮转。"""

    def __init__(
        self,
        filename: Path,
        *,
        when: str,
        interval: int,
        backup_count: int,
        max_bytes: int,
        encoding: str,
    ) -> None:
        self.max_bytes = max(0, max_bytes)
        super().__init__(
            filename,
            when=when,
            interval=max(1, interval),
            backupCount=max(1, backup_count),
            encoding=encoding,
            utc=True,
        )
        self._rollover_reason = ""
        self.suffix = "%Y-%m-%d_%H-%M-%S"
        self.extMatch = re.compile(r"^\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}(-\d{6})?(\.\w+)?$", re.ASCII)

    def shouldRollover(self, record: logging.LogRecord) -> int:
        self._rollover_reason = ""
        if super().shouldRollover(record):
            self._rollover_reason = "time"
            return 1
        if self.max_bytes <= 0:
            return 0
        if self.stream is None:
            self.stream = self._open()
        message = f"{self.format(record)}\n"
        self.stream.seek(0, 2)
        encoding = self.encoding or "utf-8"
        try:
            message_bytes = len(message.encode(encoding, errors="replace"))
        except LookupError:
            message_bytes = len(message.encode("utf-8", errors="replace"))
        if self.stream.tell() + message_bytes >= self.max_bytes:
            self._rollover_reason = "size"
            return 1
        return 0

    def doRollover(self) -> None:
        if self._rollover_reason != "size":
            super().doRollover()
            self._rollover_reason = ""
            return
        if self.stream:
            self.stream.close()
            self.stream = None
        destination = f"{self.baseFilename}.{datetime.now(UTC).strftime('%Y-%m-%d_%H-%M-%S-%f')}"
        if os.path.exists(self.baseFilename):
            self.rotate(self.baseFilename, destination)
        if not self.delay:
            self.stream = self._open()
        if os.name == "posix" and os.path.exists(self.baseFilename):
            try:
                os.chmod(self.baseFilename, 0o600)
            except OSError:
                pass
        self.rolloverAt = self.computeRollover(int(time.time()))
        for filename in self.getFilesToDelete():
            try:
                os.remove(filename)
            except OSError:
                pass
        self._rollover_reason = ""


def debug_logging_enabled() -> bool:
    return os.getenv("BLANK_DEBUG_LOG_ENABLED", "true").strip().lower() not in FALSE_VALUES


def debug_console_logging_enabled() -> bool:
    configured = os.getenv("BLANK_DEBUG_LOG_CONSOLE", "").strip().lower()
    if configured:
        return configured not in FALSE_VALUES
    return os.getenv("BLANK_ENV", "development").strip().lower() not in {"prod", "production"}


def configure_debug_logger() -> logging.Logger:
    logger = logging.getLogger(DEBUG_LOGGER_NAME)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    if logger.handlers:
        return logger
    log_path = Path(os.getenv("BLANK_DEBUG_LOG_PATH", str(BASE_DIR / "data" / "debug.log"))).expanduser()
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        if os.name == "posix":
            log_path.parent.chmod(0o700)
        file_handler: logging.Handler = PeriodicSizeRotatingFileHandler(
            log_path,
            when=os.getenv("BLANK_DEBUG_LOG_ROTATE_WHEN", "midnight").strip() or "midnight",
            interval=int(os.getenv("BLANK_DEBUG_LOG_ROTATE_INTERVAL", "1")),
            backup_count=int(os.getenv("BLANK_DEBUG_LOG_BACKUP_COUNT", "14")),
            max_bytes=int(os.getenv("BLANK_DEBUG_LOG_MAX_BYTES", str(10 * 1024 * 1024))),
            encoding="utf-8",
        )
        if os.name == "posix" and log_path.exists():
            log_path.chmod(0o600)
    except (OSError, ValueError):
        file_handler = logging.NullHandler()
    file_handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(file_handler)
    if debug_console_logging_enabled():
        console_handler = logging.StreamHandler(sys.stderr)
        console_handler.setFormatter(logging.Formatter("[blank.debug] %(message)s"))
        logger.addHandler(console_handler)
    return logger


def close_debug_logger_handlers() -> None:
    logger = logging.getLogger(DEBUG_LOGGER_NAME)
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()


debug_logger = configure_debug_logger()


def sanitize_debug_value(value: Any, limit: int = MAX_DEBUG_FIELD_CHARS) -> Any:
    if isinstance(value, dict):
        return {
            str(key): "[REDACTED]" if key_is_sensitive(str(key)) else sanitize_debug_value(item, limit)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [sanitize_debug_value(item, limit) for item in value]
    if isinstance(value, bytes):
        return sanitize_debug_text(value.decode("utf-8", errors="replace"), limit)
    if isinstance(value, str):
        return sanitize_debug_text(value, limit)
    return value


def sanitize_debug_text(value: str, limit: int = MAX_DEBUG_FIELD_CHARS) -> str:
    safe = redact_secret_text(value, limit=limit)
    if len(safe) > limit:
        return f"{safe[:limit]}...[truncated {len(safe) - limit} chars]"
    return safe


def key_is_sensitive(key: str) -> bool:
    normalized = key.strip().lower().replace("_", "-")
    return any(item in normalized for item in SENSITIVE_KEYS)


def log_debug_event(event: str, **fields: Any) -> None:
    if not debug_logging_enabled():
        return
    payload = {
        "ts": datetime.now(UTC).isoformat(),
        "event": event,
        **{key: sanitize_debug_value(value) for key, value in fields.items()},
    }
    try:
        line = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    except TypeError:
        line = json.dumps(
            {"ts": payload["ts"], "event": event, "unserializable": sanitize_debug_text(repr(fields))},
            ensure_ascii=False,
            sort_keys=True,
        )
    if len(line) > MAX_DEBUG_JSON_CHARS:
        line = f"{line[:MAX_DEBUG_JSON_CHARS]}...[debug event truncated]"
    debug_logger.info(line)
