"""Cross-platform native folder picker for local CLI and Web flows."""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import tempfile
import threading
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent
WINDOWS_PICKER_SOURCE = PROJECT_DIR / "native" / "windows_folder_picker.cs"
WINDOWS_PICKER_MANIFEST = PROJECT_DIR / "native" / "windows_folder_picker.manifest"
WINDOWS_PICKER_RUNTIME = PROJECT_DIR / "tools" / "folder-picker-runtime"
_WINDOWS_PICKER_LOCK = threading.Lock()
_WINDOWS_PICKER_EXECUTABLE: Path | None = None


class FolderPickerUnavailable(RuntimeError):
    """Raised when the current desktop session cannot show a folder picker."""


def _windows_compiler() -> Path | None:
    windows_dir = Path(os.environ.get("WINDIR", r"C:\Windows"))
    candidates = (
        windows_dir / "Microsoft.NET" / "Framework64" / "v4.0.30319" / "csc.exe",
        windows_dir / "Microsoft.NET" / "Framework" / "v4.0.30319" / "csc.exe",
    )
    return next((path for path in candidates if path.is_file()), None)


def folder_picker_available() -> bool:
    """Return whether this platform has a supported native picker strategy."""
    if sys.platform == "win32":
        return _windows_compiler() is not None
    return sys.platform == "darwin"


def _run_picker(command: list[str], env: dict[str, str] | None = None):
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        check=False,
    )


def _windows_picker_digest() -> str:
    digest = hashlib.sha256()
    for path in (WINDOWS_PICKER_SOURCE, WINDOWS_PICKER_MANIFEST):
        digest.update(path.read_bytes())
    return digest.hexdigest()[:16]


def prepare_windows_picker() -> Path:
    """Compile the DPI-aware STA helper once and reuse it for every click."""
    global _WINDOWS_PICKER_EXECUTABLE
    if sys.platform != "win32":
        raise FolderPickerUnavailable("Windows 文件夹选择器只能在 Windows 上准备")
    if _WINDOWS_PICKER_EXECUTABLE and _WINDOWS_PICKER_EXECUTABLE.is_file():
        return _WINDOWS_PICKER_EXECUTABLE

    with _WINDOWS_PICKER_LOCK:
        if _WINDOWS_PICKER_EXECUTABLE and _WINDOWS_PICKER_EXECUTABLE.is_file():
            return _WINDOWS_PICKER_EXECUTABLE
        compiler = _windows_compiler()
        if compiler is None:
            raise FolderPickerUnavailable("未找到 Windows .NET Framework C# 编译器")
        try:
            digest = _windows_picker_digest()
        except OSError as error:
            raise FolderPickerUnavailable("无法读取 Windows 文件夹选择器源码") from error

        WINDOWS_PICKER_RUNTIME.mkdir(parents=True, exist_ok=True)
        executable = WINDOWS_PICKER_RUNTIME / f"folder-picker-{digest}.exe"
        if not executable.is_file():
            temporary = WINDOWS_PICKER_RUNTIME / f".{executable.name}.tmp.exe"
            command = [
                str(compiler),
                "/nologo",
                "/target:winexe",
                "/optimize+",
                f"/win32manifest:{WINDOWS_PICKER_MANIFEST}",
                f"/out:{temporary}",
                str(WINDOWS_PICKER_SOURCE),
            ]
            creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            try:
                result = subprocess.run(
                    command,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    check=False,
                    timeout=30,
                    creationflags=creation_flags,
                )
            except (OSError, subprocess.TimeoutExpired) as error:
                raise FolderPickerUnavailable("编译 Windows 文件夹选择器失败") from error
            if result.returncode != 0 or not temporary.is_file():
                detail = (result.stderr or result.stdout).strip()
                raise FolderPickerUnavailable(
                    detail or "编译 Windows 文件夹选择器失败"
                )
            os.replace(temporary, executable)
        _WINDOWS_PICKER_EXECUTABLE = executable
        return executable


def _choose_windows(initial_dir: Path) -> str | None:
    executable = prepare_windows_picker()
    descriptor, result_name = tempfile.mkstemp(
        prefix="mvd-folder-picker-",
        suffix=".txt",
    )
    os.close(descriptor)
    result_path = Path(result_name)
    # app.py is normally launched with a hidden console window. Explicitly
    # request a normally shown GUI child; otherwise Windows can carry the
    # hidden startup state into IFileDialog.Show and leave the HTTP request
    # waiting on an invisible picker.
    startup_info = subprocess.STARTUPINFO()
    startup_info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startup_info.wShowWindow = 1  # SW_SHOWNORMAL
    try:
        result = subprocess.run(
            [str(executable), str(initial_dir), str(result_path)],
            capture_output=True,
            check=False,
            timeout=600,
            startupinfo=startup_info,
        )
        text = result_path.read_text(encoding="utf-8").strip()
        if result.returncode == 2:
            return None
        if result.returncode != 0:
            raise FolderPickerUnavailable(
                text.removeprefix("ERROR:").strip()
                or "Windows 文件夹选择器启动失败"
            )
        return text or None
    except subprocess.TimeoutExpired as error:
        raise FolderPickerUnavailable("文件夹选择窗口等待超时，请重试") from error
    except OSError as error:
        raise FolderPickerUnavailable("Windows 文件夹选择器启动失败") from error
    finally:
        try:
            result_path.unlink(missing_ok=True)
        except OSError:
            pass


def validate_windows_picker() -> bool:
    """Run a no-UI COM smoke test in the same helper used by Web requests."""
    executable = prepare_windows_picker()
    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    result = subprocess.run(
        [str(executable), "--validate"],
        capture_output=True,
        check=False,
        timeout=10,
        creationflags=creation_flags,
    )
    return result.returncode == 0


def _choose_macos(initial_dir: Path) -> str | None:
    script = """
on run argv
    try
        set startFolder to POSIX file (item 1 of argv)
        return POSIX path of (choose folder with prompt "选择下载文件夹" default location startFolder)
    on error number -128
        return ""
    end try
end run
"""
    result = _run_picker(
        ["osascript", "-e", script, str(initial_dir)],
        dict(os.environ),
    )
    if result.returncode != 0:
        raise FolderPickerUnavailable(
            result.stderr.strip() or "macOS 文件夹选择器启动失败"
        )
    return result.stdout.strip() or None


def prepare_folder_picker() -> None:
    """Warm platform-specific picker dependencies during Web startup."""
    if sys.platform == "win32":
        prepare_windows_picker()


def choose_folder(initial_dir: str | Path) -> str | None:
    """Open the native folder picker and return an absolute path or None."""
    initial = Path(initial_dir).expanduser().resolve(strict=False)
    if sys.platform == "win32":
        return _choose_windows(initial)
    if sys.platform == "darwin":
        return _choose_macos(initial)
    raise FolderPickerUnavailable("当前系统不支持原生文件夹选择器，请手动输入路径")
