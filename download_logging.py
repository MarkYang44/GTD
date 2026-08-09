"""Redacted, rotating JSON Lines logging for download events."""

from __future__ import annotations

import json
import logging
import re
import threading
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

PROJECT_DIR = Path(__file__).resolve().parent
SENSITIVE_KEYS = {
    "access_token",
    "api_key",
    "authorization",
    "cookie",
    "cookies",
    "password",
    "proxy_authorization",
    "proxy_password",
    "proxy_username",
    "refresh_token",
    "session",
    "session_id",
    "token",
}
URL_RE = re.compile(r"https?://[^\s]+", re.IGNORECASE)
SECRET_TEXT_RE = re.compile(
    r"(?i)\b(authorization|cookie|(?:access[_-]?|refresh[_-]?)?token|"
    r"password|api[_-]?key|session(?:[_-]?id)?|"
    r"proxy[_-]?(?:authorization|username|password))"
    r"\s*[:=]\s*[^\r\n]*"
)
SECRET_HEADER_RE = re.compile(
    r"(?im)\b(authorization|proxy-authorization|cookie)\s*[:=]\s*[^\r\n]*"
)
_warning_lock = threading.Lock()
_warning_emitted = False


def _warn_logging_once() -> None:
    global _warning_emitted
    with _warning_lock:
        if not _warning_emitted:
            print("⚠️  下载日志暂时无法写入，下载任务将继续执行。")
            _warning_emitted = True


def sanitize_url(value: object) -> str:
    """Keep a page identity while removing credentials, query, and fragment."""
    text = str(value)
    try:
        parts = urlsplit(text)
    except ValueError:
        return "[redacted-url]"
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        return text
    host = parts.hostname
    if parts.port:
        host = f"{host}:{parts.port}"
    return urlunsplit((parts.scheme, host, parts.path, "", ""))


def _redact_text(value: str) -> str:
    redacted = SECRET_HEADER_RE.sub(
        lambda match: f"{match.group(1)}=[redacted]",
        value,
    )
    redacted = SECRET_TEXT_RE.sub(
        lambda match: f"{match.group(1)}=[redacted]",
        redacted,
    )
    return URL_RE.sub(lambda match: sanitize_url(match.group(0)), redacted)


def redact_value(value: Any, key: str = "") -> Any:
    """Recursively redact secrets and signed URL parameters."""
    normalized_key = key.lower().replace("-", "_")
    key_parts = set(normalized_key.split("_"))
    if (
        normalized_key in SENSITIVE_KEYS
        or "authorization" in key_parts
        or "cookie" in key_parts
        or "password" in key_parts
        or "secret" in key_parts
        or "session" in key_parts
        or "token" in key_parts
        or normalized_key.endswith("_api_key")
    ):
        return "[redacted]"
    if isinstance(value, dict):
        return {
            str(child_key): redact_value(child_value, str(child_key))
            for child_key, child_value in value.items()
        }
    if isinstance(value, (list, tuple, set)):
        return [redact_value(item) for item in value]
    if isinstance(value, str):
        return _redact_text(value)
    return value


class JsonLineFormatter(logging.Formatter):
    """Render one compact JSON object per log record."""

    def format(self, record: logging.LogRecord) -> str:
        payload = redact_value(record.payload)
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def get_download_logger(log_dir: Path | None = None) -> logging.Logger | None:
    """Build one logger per directory without making logging mandatory."""
    directory = Path(log_dir) if log_dir else PROJECT_DIR / "logs"
    try:
        directory.mkdir(parents=True, exist_ok=True)
        resolved = directory.resolve()
        logger = logging.getLogger(f"multiple_video_downloader.{resolved}")
        logger.setLevel(logging.INFO)
        logger.propagate = False
        if not logger.handlers:
            handler = RotatingFileHandler(
                directory / "downloader.jsonl",
                maxBytes=10 * 1024 * 1024,
                backupCount=5,
                encoding="utf-8",
            )
            handler.setFormatter(JsonLineFormatter())
            logger.addHandler(handler)
        return logger
    except OSError:
        _warn_logging_once()
        return None


def log_download_event(
    logger: logging.Logger | None,
    event: str,
    **fields: object,
) -> bool:
    """Write a safe event; logging failures never fail a download."""
    if logger is None:
        return False
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event": event,
        "batch_id": None,
        "task_id": None,
        "attempt_number": None,
        "platform": None,
        "media_type": None,
        "audio_format": None,
        "speed_mode": None,
        "elapsed_seconds": None,
        "status": None,
        "error_code": None,
        **fields,
    }
    try:
        logger.info("download-event", extra={"payload": payload})
    except (OSError, ValueError):
        _warn_logging_once()
        return False
    return True
