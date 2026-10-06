#!/usr/bin/env python3
"""Freeze GTD from an explicit public-resource manifest; never copy source state."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PUBLIC_EXTENSIONS = {'.html', '.css', '.js', '.json', '.png', '.jpg', '.jpeg', '.webp', '.svg', '.ico', '.woff', '.woff2', '.ttf', '.mp3', '.mp4', '.wav', '.webmanifest'}

def public_resources(root=ROOT):
    result = []
    for folder in ('templates', 'static', 'assets/fallback_covers'):
        for path in sorted((root / folder).rglob('*')):
            if path.is_file() and not path.is_symlink() and path.suffix.lower() in PUBLIC_EXTENSIONS and not any(p.startswith('.') for p in path.relative_to(root).parts):
                result.append((path, path.relative_to(root).parent.as_posix()))
    for path in sorted((root / 'data/lmu').glob('*.json')):
        if path.name == 'releases.json' or path.name == 'baseline-import.json' or (path.name[0:4].isdigit() and len(path.name.split('.')) == 5):
            result.append((path, 'data/lmu'))
    for relative in ('data/lmu/calendar/current.json', 'data/lmu/calendar/schema.json', 'docs/WEB_GUIDE.md', 'docs/WEB_GUIDE.en.md', 'docs/DESKTOP.md', 'native/windows_folder_picker.cs', 'native/windows_folder_picker.manifest'):
        path = root / relative
        if path.is_file() and not path.is_symlink():
            result.append((path, Path(relative).parent.as_posix()))
    return result

def validate_tools(directory, windows=None):
    windows = os.name == 'nt' if windows is None else windows
    for name in ('ffmpeg', 'ffprobe', 'aria2c', 'node'):
        path = directory / 'bin' / (name + ('.exe' if windows else ''))
        if not path.is_file():
            raise RuntimeError(f'Missing bundled tool {name}: run scripts/prepare_desktop_tools.py')
    if not (directory / 'notices/manifest.json').is_file():
        raise RuntimeError('Missing tool provenance manifest')

def build(tools_dir):
    validate_tools(tools_dir)
    os.environ.setdefault('PYINSTALLER_CONFIG_DIR', str(ROOT / 'build/pyinstaller-cache'))
    resources = public_resources()
    common = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--onedir', '--distpath', str(ROOT / 'dist'), '--workpath', str(ROOT / 'build/desktop'), '--specpath', str(ROOT / 'build/desktop'), '--paths', str(ROOT)]
    for source, destination in resources:
        common += ['--add-data', f'{source}{os.pathsep}{destination}']
    common += ['--add-data', f'{tools_dir}{os.pathsep}tools/desktop-bin']
    for package in ('yt_dlp', 'yt_dlp_ejs', 'curl_cffi', 'certifi'):
        common += ['--collect-all', package]
    for distribution in ('yt-dlp', 'Flask', 'mutagen', 'PySide6'):
        common += ['--recursive-copy-metadata', distribution]
    # The CLI is independently frozen, preserving stdin and main.py's original argv.
    subprocess.run(common + ['--name', 'GTD-CLI', '--console', str(ROOT / 'desktop_cli.py')], check=True, cwd=ROOT)
    subprocess.run(common + ['--name', 'GTD', '--windowed', '--hidden-import', 'PySide6.QtWebEngineCore', '--hidden-import', 'PySide6.QtWebEngineWidgets', str(ROOT / 'desktop.py')], check=True, cwd=ROOT)
    artifact = ROOT / 'dist/GTD.app' if sys.platform == 'darwin' else ROOT / 'dist/GTD'
    if sys.platform == 'darwin':
        cli_destination = artifact / 'Contents/Resources/cli'
    else:
        cli_destination = artifact / 'cli'
    shutil.copytree(ROOT / 'dist/GTD-CLI', cli_destination, dirs_exist_ok=True)
    if sys.platform == 'darwin':
        subprocess.run(['codesign', '--force', '--deep', '--sign', '-', str(artifact)], check=True)
    zip_path = ROOT / 'dist' / f'GTD-{platform.system().lower()}-{platform.machine()}.zip'
    # ditto preserves app symlinks/permissions, essential for Qt frameworks.
    if sys.platform == 'darwin':
        subprocess.run(['ditto', '-c', '-k', '--sequesterRsrc', '--keepParent', str(artifact), str(zip_path)], check=True)
    else:
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as archive:
            for path in artifact.rglob('*'):
                if path.is_file():
                    archive.write(path, path.relative_to(artifact.parent))
    with zip_path.open('rb') as archive:
        digest = hashlib.file_digest(archive, 'sha256').hexdigest()
    zip_path.with_suffix('.zip.sha256').write_text(f'{digest}  {zip_path.name}\n')
    (ROOT / 'dist/resource-manifest.json').write_text(json.dumps([p.relative_to(ROOT).as_posix() for p, _ in resources], indent=2))
    print(zip_path)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tools-dir', type=Path, default=ROOT / 'tools/desktop-bin')
    args = parser.parse_args()
    build(args.tools_dir.resolve())
