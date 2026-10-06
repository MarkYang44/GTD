# GTD Desktop / 桌面版

GTD Desktop preserves the existing downloader, local audio tools and LMU routes in a QtWebEngine window. macOS packages target Apple Silicon; Windows packages target x64. Keep the complete application/portable directory. Python and system media tools are unnecessary for packaged use.

GTD 桌面版保留下载、本地音频和 LMU 全部页面。macOS 为 Apple Silicon，Windows 为 x64。便携版请保留整个目录；运行打包产物无需 Python 或系统媒体工具。

## Build / 构建

Use Python 3.13 (local Python 3.14 is also supported by the pinned build dependencies).

```sh
python3 -m venv .venv-desktop
.venv-desktop/bin/python -m pip install -r requirements-build.txt
.venv-desktop/bin/python scripts/prepare_desktop_tools.py
.venv-desktop/bin/python scripts/build_desktop.py
```

On macOS, preparation requires installed Homebrew FFmpeg, aria2 and Node. The preparer copies every transitive non-system dylib, rewrites load paths, verifies there are no remaining Homebrew dependency paths, and ad-hoc signs copied Mach-O files. End users do not need Homebrew. Build output: `dist/GTD.app`, platform ZIP, SHA256 and public-resource manifest.

Windows: install Python 3.13 x64 for building, then double-click **Build Desktop.cmd**. It creates `.venv-desktop`, installs fixed Python dependencies, downloads media tools, and produces `dist/GTD/GTD.exe` plus ZIP/SHA256. **Desktop.cmd** launches the built app, or the installed source environment. GitHub Actions builds Windows on pushes to `codex/gtd-desktop` or manual dispatch, uploading artifacts without publishing a Release.

Windows 构建需要 Python 3.13 x64，双击 **Build Desktop.cmd** 即可；完成后运行 `dist/GTD/GTD.exe`。GitHub Actions 的构建产物位于对应运行的 Artifacts，需解压整个 ZIP。

CLI companion: macOS `GTD.app/Contents/Resources/cli/GTD-CLI`; Windows `GTD/cli/GTD-CLI.exe`. Run it in a terminal to preserve interactive input and command-line arguments.

## Data / 数据

Writable state lives in `~/Library/Application Support/GTD` on macOS and `%LOCALAPPDATA%/GTD` on Windows. Default downloads: `~/Downloads/GTD`. Desktop settings provide explicit imports; source cookies/history/downloads are not copied into the application. Public LMU snapshots and current published calendar are bundled; calendar imports, backups/status/locks, logs, database history, cookies, environments and Git data are excluded.

用户数据保存在系统应用数据目录；默认下载目录为 Downloads/GTD。原项目私有数据不随包分发，设置中可选择导入。升级时保留数据目录。

## Third-party notices / 第三方许可

`tools/desktop-bin/notices` accompanies each package, containing source URLs, binary SHA256, original license/readme files and Homebrew formula metadata. Node 22.16.0 Windows binaries are verified against Node's published SHA256 list; Gyan FFmpeg is verified against its published SHA256. aria2 1.37.0 official GitHub binaries have no separate publisher checksum; their audited SHA256 is pinned in the preparer. All three Windows archives are pinned to audited SHA256 values. Gyan's FFmpeg URL tracks releases, but the preparer locks the audited 9.0.2 archive hash; a changed upstream release fails the build until its pin is reviewed. Exact hashes and source URLs are recorded per build. Download uses HTTPS; builds should retain their provenance manifest.

FFmpeg distributions may enable GPL components; aria2 is GPL; Node is MIT with additional notices. PySide6/Qt use LGPL/commercial terms and are dynamically linked. PyInstaller has its bootloader distribution exception. Original notices and source/build URLs remain in the bundle; redistributors must meet applicable source/license obligations. This project does not claim that GPL tools are MIT licensed. Python package license metadata is collected with the build.

macOS packages use ad-hoc signing, not Apple Developer signing/notarization. No Windows native UI validation is claimed from a macOS build. Actual test results belong in the delivery verification report.

## Windows user verification / Windows 验收

1. Verify the ZIP against `.sha256`, extract to a path containing spaces, then launch `GTD.exe`.
2. Open downloader, local audio and every LMU route; switch theme/language and restart to check persistence.
3. Select a download folder through the native picker; process a small local clip into MP3 or source audio and save a result; verify WAV separately through the URL download format.
4. Check bundled FFmpeg/ffprobe/aria2/Node capability indicators with no system tools on PATH.
5. Exercise a real supported URL, playlist selection, cancellation/history retry and Cookie import as needed.
6. Close while a task runs and verify confirmation/cancellation; restart and verify history and favorites remain.
7. Launch `cli/GTD-CLI.exe` from a terminal and verify original interactive/argument behavior.

If a launch fails, record Windows version, ZIP SHA256, screenshot/error text and application logs. CI compilation establishes build evidence; this checklist establishes native runtime behavior.
