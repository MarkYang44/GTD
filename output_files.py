"""Filesystem helpers for download directories and finalized media outputs."""

from __future__ import annotations

import os
import re
import shutil
import uuid
from pathlib import Path
from typing import Any


PROJECT_DIR = Path(__file__).resolve().parent
DOWNLOADS_DIR = PROJECT_DIR / "downloads"
ATTEMPT_OUTPUT_MARKER_RE = re.compile(r" \[\.__mvd_[A-Za-z0-9_-]+\]$")

_PREPARED_OUTPUT_DIR_CAPABILITY = object()


class _PreparedOutputDir(str):
    """A private capability created only after full directory validation."""

    def __new__(cls, path: Path, capability: object):
        prepared = super().__new__(cls, str(path))
        prepared.path = path
        prepared.capability = capability
        return prepared


def ensure_downloads_dir(
    download_dir: str | Path | None = None,
    *,
    project_dir: Path = PROJECT_DIR,
    downloads_dir: Path = DOWNLOADS_DIR,
    path_cls: type[Path] = Path,
    os_module: Any = os,
    uuid_module: Any = uuid,
) -> Path:
    """Resolve, create, and verify a user-selected download directory."""
    if download_dir is None or (
        isinstance(download_dir, str) and not download_dir.strip()
    ):
        target = downloads_dir
    elif not isinstance(download_dir, (str, os_module.PathLike)):
        raise ValueError("下载目录必须是路径字符串")
    else:
        raw = os_module.path.expandvars(str(download_dir).strip())
        if "\x00" in raw:
            raise ValueError("下载目录包含无效字符")
        if os_module.name != "nt" and re.match(r"^[A-Za-z]:[\\/]", raw):
            raise ValueError("当前系统不能使用 Windows 盘符路径")
        path = path_cls(raw).expanduser()
        target = path if path.is_absolute() else project_dir / path

    try:
        target = target.resolve(strict=False)
        target.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise ValueError(f"无法创建下载目录: {target}") from error
    if not target.is_dir():
        raise ValueError(f"下载位置不是文件夹: {target}")

    probe = target / f".__mvd_write_test_{uuid_module.uuid4().hex}.tmp"
    try:
        with probe.open("x", encoding="utf-8") as handle:
            handle.write("ok")
        probe.unlink()
    except OSError as error:
        try:
            probe.unlink(missing_ok=True)
        except OSError:
            pass
        raise ValueError(f"下载目录不可写: {target}") from error
    return target


def prepare_output_dir(
    download_dir: str | Path | None,
    *,
    ensure_directory=ensure_downloads_dir,
) -> _PreparedOutputDir:
    """Fully validate a batch directory and create its private capability."""
    return _PreparedOutputDir(
        ensure_directory(download_dir), _PREPARED_OUTPUT_DIR_CAPABILITY
    )


def prepared_output_dir(prepared: object) -> Path:
    """Read a previously validated directory without repeating its write probe."""
    if not isinstance(prepared, _PreparedOutputDir) or (
        prepared.capability is not _PREPARED_OUTPUT_DIR_CAPABILITY
    ):
        raise ValueError("已验证下载目录必须由内部批次准备")
    if not prepared.path.is_absolute() or not prepared.path.is_dir():
        raise ValueError(f"下载位置不是文件夹: {prepared.path}")
    return prepared.path


def validate_output_version(output_version: int) -> None:
    if (
        isinstance(output_version, bool)
        or not isinstance(output_version, int)
        or output_version < 1
    ):
        raise ValueError("输出版本必须是大于等于 1 的整数")


def output_template(platform: str, output_dir: Path, output_version: int) -> str:
    suffix = "" if output_version == 1 else f" ({output_version})"
    name = (
        f"%(title)s [%(id)s]{suffix}.%(ext)s"
        if platform in {"instagram", "bilibili"}
        else f"%(title)s{suffix}.%(ext)s"
    )
    return str(output_dir / name)


def attempt_output_template(
    platform: str, output_dir: Path, attempt_workspace: Path
) -> str:
    """Use an attempt-unique working name before atomic final claiming."""
    base = "%(title)s [%(id)s]" if platform in {"instagram", "bilibili"} else "%(title)s"
    return str(output_dir / f"{base} [.__mvd_{attempt_workspace.name}].%(ext)s")


def new_attempt_workspace(
    output_dir: Path, *, uuid_module: Any = uuid
) -> Path:
    """Create a private temporary directory owned by one download attempt."""
    root = output_dir / ".attempts"
    root.mkdir(parents=True, exist_ok=True)
    workspace = root / uuid_module.uuid4().hex
    workspace.mkdir()
    return workspace


def cleanup_attempt_workspace(
    workspace: Path, *, path_cls: type[Path] = Path, shutil_module: Any = shutil
) -> None:
    """Delete only a workspace created for one download attempt."""
    workspace = path_cls(workspace)
    if workspace.parent.name != ".attempts":
        raise ValueError("拒绝清理非任务临时目录")
    shutil_module.rmtree(workspace, ignore_errors=True)
    try:
        workspace.parent.rmdir()
    except OSError:
        pass


def claim_final_output_with_version(
    filepath: Path,
    final_stem: str,
    output_version: int,
    *,
    os_module: Any = os,
) -> tuple[Path, int]:
    """Atomically claim a no-overwrite final path in the same directory."""
    validate_output_version(output_version)
    version = output_version
    while True:
        suffix = "" if version == 1 else f" ({version})"
        target = filepath.with_name(f"{final_stem}{suffix}{filepath.suffix}")
        try:
            os_module.link(filepath, target)
        except FileExistsError:
            version += 1
            continue
        filepath.unlink()
        return target, version


def claim_final_output(
    filepath: Path, final_stem: str, output_version: int, *, os_module: Any = os
) -> Path:
    return claim_final_output_with_version(
        filepath, final_stem, output_version, os_module=os_module
    )[0]


def finalize_video_output_with_version(
    filepath: Path,
    output_version: int = 1,
    *,
    os_module: Any = os,
    claim_output=None,
) -> tuple[Path, int]:
    """Remove the private marker and atomically reserve the visible filename."""
    final_stem = ATTEMPT_OUTPUT_MARKER_RE.sub("", filepath.stem)
    if final_stem == filepath.stem:
        return filepath, output_version
    if claim_output is not None:
        return claim_output(filepath, final_stem, output_version)
    return claim_final_output_with_version(
        filepath, final_stem, output_version, os_module=os_module
    )


def finalize_video_output(
    filepath: Path, output_version: int = 1, *, os_module: Any = os, claim_output=None
) -> Path:
    return finalize_video_output_with_version(
        filepath, output_version, os_module=os_module, claim_output=claim_output
    )[0]


def audio_output_version(filepath: Path, requested: int) -> int:
    """Read the version suffix added after an audio quality label."""
    match = re.search(r"\[[^\]]+\] \((\d+)\)$", filepath.stem)
    return max(requested, int(match.group(1))) if match else requested


def resolve_output_path(
    ydl: Any,
    info: dict,
    output_dir: Path,
    media_type: str = "video",
    audio_format: str = "mp3",
    audio_profile: Any = None,
    audio_output_ext: str | None = None,
    *,
    path_cls: type[Path] = Path,
) -> Path:
    """Locate yt-dlp's actual postprocessed output file."""
    if audio_format not in {"mp3", "flac", "source", "wav"}:
        raise ValueError(f"不支持的音频格式: {audio_format}")
    prepared = path_cls(ydl.prepare_filename(info))
    output_ext = (
        audio_output_ext
        or (audio_profile.output_ext if audio_profile is not None else None)
        or audio_format
    )
    output_suffix = f".{output_ext}" if media_type == "audio" else ".mp4"
    candidates = [prepared.with_suffix(output_suffix), prepared]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    matches = sorted(
        output_dir.glob(f"{prepared.stem}.*"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    return matches[0] if matches else prepared.with_suffix(output_suffix)


def format_filesize(filepath: Path, info: dict) -> str:
    """Prefer the final on-disk file size over extractor metadata."""
    if filepath.is_file():
        size = filepath.stat().st_size
    else:
        size = info.get("filesize_approx") or info.get("filesize")
    return f"{size / (1024 * 1024):.2f} MB" if size else "未知（请查看文件）"


# Compatibility spellings for callers moving from downloader.py.
_prepare_output_dir = prepare_output_dir
_prepared_output_dir = prepared_output_dir
_validate_output_version = validate_output_version
_output_template = output_template
_attempt_output_template = attempt_output_template
_new_attempt_workspace = new_attempt_workspace
_cleanup_attempt_workspace = cleanup_attempt_workspace
_claim_final_output = claim_final_output
_claim_final_output_with_version = claim_final_output_with_version
_finalize_video_output = finalize_video_output
_finalize_video_output_with_version = finalize_video_output_with_version
_audio_output_version = audio_output_version
_resolve_output_path = resolve_output_path
_format_filesize = format_filesize
