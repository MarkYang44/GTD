"""Stable, user-facing download error information."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DownloadErrorInfo:
    """Public guidance plus a private diagnostic detail."""

    error_code: str
    message: str
    suggestion: str
    retryable: bool
    technical_detail: str = ""


class DownloadFailure(Exception):
    """Exception carrying a classified download failure."""

    def __init__(self, info: DownloadErrorInfo):
        super().__init__(info.technical_detail or info.message)
        self.info = info


class DownloadCancelled(DownloadFailure):
    """Cooperative task cancellation, distinct from a failure."""

    def __init__(self):
        super().__init__(
            DownloadErrorInfo(
                error_code="CANCELLED",
                message="任务已取消",
                suggestion="可以点击重试重新加入队列",
                retryable=True,
            )
        )


def _info(
    code: str,
    message: str,
    suggestion: str,
    retryable: bool,
    detail: str,
) -> DownloadErrorInfo:
    return DownloadErrorInfo(code, message, suggestion, retryable, detail)


def classify_download_error(
    error: BaseException,
    platform: str | None = None,
    stage: str = "download",
) -> DownloadErrorInfo:
    """Convert third-party exceptions into a stable project error."""
    if isinstance(error, DownloadFailure):
        return error.info

    detail = str(error)
    message = detail.lower()

    if "timeout" in message or "timed out" in message:
        return _info(
            "NETWORK_TIMEOUT",
            "网络连接源站超时",
            "请检查网络或代理设置后重试",
            True,
            detail,
        )
    if any(
        marker in message
        for marker in ("http error 429", "rate limit", "too many request")
    ):
        return _info(
            "RATE_LIMITED",
            "请求过于频繁",
            "请稍后再重试，并避免同时提交大量链接",
            True,
            detail,
        )
    if platform == "bilibili" and any(
        marker in message
        for marker in ("members only", "member only", "premium")
    ):
        return _info(
            "MEMBERSHIP_REQUIRED",
            "该内容需要会员权限",
            "请确认当前 Cookie 对应账号拥有访问权限",
            False,
            detail,
        )
    if any(
        marker in message
        for marker in ("login", "sign in", "http error 403", "private")
    ):
        return _info(
            "AUTH_REQUIRED",
            "当前凭证无法访问该内容",
            "请更新对应平台 Cookie 后重试",
            True,
            detail,
        )
    if any(
        marker in message
        for marker in ("copyright", "geo", "region", "blocked")
    ):
        return _info(
            "GEO_RESTRICTED",
            "该内容受到版权或地区限制",
            "请确认当前地区允许访问该内容",
            False,
            detail,
        )
    if "requested format" in message or "no audio" in message:
        return _info(
            "FORMAT_UNAVAILABLE",
            "源站没有可用的目标格式",
            "请选择其他输出格式或更换链接",
            False,
            detail,
        )
    if "aria2" in message:
        return _info(
            "ARIA2_FAILED",
            "aria2c 极速下载失败",
            "请重试；程序会按现有规则降级到标准模式",
            True,
            detail,
        )
    if "ffmpeg" in message or "ffprobe" in message or stage == "postprocess":
        return _info(
            "POSTPROCESS_FAILED",
            "媒体后处理失败",
            "请确认 FFmpeg 可用且磁盘空间充足",
            True,
            detail,
        )
    if stage == "collection":
        return _info(
            "COLLECTION_EXTRACT_FAILED",
            "无法解析播放列表或合集",
            "请确认链接公开可访问并更新 Cookie 后重试",
            True,
            detail,
        )
    if stage == "metadata":
        return _info(
            "METADATA_FAILED",
            "无法读取媒体信息",
            "请检查链接、Cookie 和网络后重试",
            True,
            detail,
        )
    if isinstance(error, OSError):
        return _info(
            "STORAGE_ERROR",
            "无法写入下载文件",
            "请检查下载目录权限和磁盘空间",
            True,
            detail,
        )
    return _info(
        "DOWNLOAD_FAILED",
        "下载失败",
        "请查看错误日志后重试",
        True,
        detail,
    )


def public_error(
    error: DownloadErrorInfo | DownloadFailure,
) -> dict[str, object]:
    """Return only fields safe to expose through Web or CLI surfaces."""
    info = error.info if isinstance(error, DownloadFailure) else error
    return {
        "error_code": info.error_code,
        "message": info.message,
        "suggestion": info.suggestion,
        "retryable": info.retryable,
    }


def format_cli_error(error: DownloadErrorInfo | DownloadFailure) -> str:
    """Format a localized CLI error without technical details."""
    info = error.info if isinstance(error, DownloadFailure) else error
    return f"[{info.error_code}] {info.message}\n   建议：{info.suggestion}"
