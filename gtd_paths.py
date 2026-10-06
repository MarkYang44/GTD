"""Separate immutable application resources from writable desktop user data."""
from __future__ import annotations

import os
import sys
from pathlib import Path


def resource_root() -> Path:
    return Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))


def user_data_root(platform: str | None = None, home: Path | None = None, env=None) -> Path:
    platform = sys.platform if platform is None else platform
    home = Path.home() if home is None else home
    env = os.environ if env is None else env
    if platform == 'win32':
        return Path(env.get('LOCALAPPDATA', home / 'AppData/Local')) / 'GTD'
    if platform == 'darwin':
        return home / 'Library/Application Support/GTD'
    return Path(env.get('XDG_DATA_HOME', home / '.local/share')) / 'GTD'


def runtime_root() -> Path:
    if os.environ.get('GTD_DESKTOP') == '1':
        return Path(os.environ.get('GTD_DATA_DIR', user_data_root())).expanduser()
    return resource_root()


def downloads_root() -> Path:
    if os.environ.get('GTD_DESKTOP') == '1':
        return Path(os.environ.get('GTD_DOWNLOAD_DIR', Path.home() / 'Downloads/GTD')).expanduser()
    return resource_root() / 'downloads'


def initialize_desktop(root: Path | None = None) -> Path:
    root = (root or Path(os.environ.get('GTD_DATA_DIR', user_data_root()))).expanduser().resolve()
    os.environ['GTD_DESKTOP'] = '1'
    os.environ['GTD_DATA_DIR'] = str(root)
    for name in ('state', 'logs', 'browser-profile', 'data/lmu/calendar'):
        (root / name).mkdir(parents=True, exist_ok=True)
    seed = resource_root() / 'data/lmu/calendar/current.json'
    target = root / 'data/lmu/calendar/current.json'
    # Exclusive create never overwrites a user's maintained calendar.
    if seed.is_file():
        try:
            with target.open('xb') as out:
                out.write(seed.read_bytes())
        except FileExistsError:
            pass
    os.environ.setdefault('GTD_HISTORY_PATH', str(root / 'state/tasks.sqlite3'))
    os.environ.setdefault('GTD_LMU_CALENDAR_DIR', str(root / 'data/lmu/calendar'))
    tools = str(resource_root() / 'tools/desktop-bin/bin')
    existing = os.environ.get('PATH', '').split(os.pathsep)
    os.environ['PATH'] = os.pathsep.join([tools, *[part for part in existing if part != tools]])
    return root
