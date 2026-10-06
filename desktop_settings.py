"""Bounded, validated imports for the desktop settings panel (no Qt dependency)."""
import json
import math
from http.cookiejar import NETSCAPE_MAGIC_RGX
import os
from pathlib import Path
import sqlite3
import tempfile
from contextlib import closing

MAX_COOKIE_BYTES = 4 * 1024 * 1024
MAX_HISTORY_BYTES = 64 * 1024 * 1024

def read_bounded(path, limit):
    with Path(path).open('rb') as stream:
        value = stream.read(limit + 1)
    if len(value) > limit:
        raise ValueError('Import file exceeds the size limit.')
    return value

def atomic_write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.' + path.name, dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(value); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)
    return path

def import_cookies(source, root, platform):
    if platform not in ('youtube', 'instagram', 'bilibili'):
        raise ValueError('Unsupported Cookie platform.')
    raw = read_bounded(source, MAX_COOKIE_BYTES)
    try: text = raw.decode('utf-8-sig')
    except UnicodeDecodeError: raise ValueError('Cookie file must be UTF-8 Netscape format.') from None
    if not text.splitlines() or not NETSCAPE_MAGIC_RGX.match(text.splitlines()[0]):
        raise ValueError('Cookie file requires a Netscape header.')
    rows = 0
    for line in text.splitlines():
        if line.startswith('#HttpOnly_'): line = line[10:]
        elif not line.strip() or line.startswith('#'): continue
        columns = line.split('\t')
        if (len(columns) != 7 or not columns[0] or columns[1] not in ('TRUE','FALSE')
                or (columns[1]=='TRUE') != columns[0].startswith('.')
                or not columns[2].startswith('/') or columns[3] not in ('TRUE','FALSE')
                or (columns[4] != '' and not columns[4].isdigit()) or not columns[5] or '\x00' in line):
            raise ValueError('Invalid Netscape Cookie file.')
        rows += 1
    if not rows: raise ValueError('Cookie file contains no cookies.')
    return atomic_write(Path(root) / (platform + '_cookies.txt'), text.encode('utf-8'))

def validate_favorites(value):
    if not isinstance(value, dict) or set(value) != {'circuits', 'cars'}:
        raise ValueError('Favorites must contain circuits and cars arrays.')
    result = {}
    for key in ('circuits','cars'):
        entries = value[key]
        if not isinstance(entries, list) or len(entries) > 1000 or any(not isinstance(x,str) or not x or len(x)>200 for x in entries):
            raise ValueError('Invalid favorites entries.')
        result[key] = list(dict.fromkeys(entries))
    return result

def import_calendar(source, root):
    from lmu_calendar import read_calendar, publish_calendar
    return publish_calendar(read_calendar(Path(source)), Path(root) / 'data/lmu/calendar')


def validate_history_batch(batch, identifier, created, task_ids):
    def finite(value): return type(value) in (int,float) and math.isfinite(value)
    def valid_string(value): return isinstance(value,str) and bool(value) and len(value)<16384
    if (not isinstance(batch,dict) or not valid_string(identifier) or batch.get('id') != identifier
            or not finite(created) or not finite(batch.get('created_at')) or batch['created_at'] != created
            or not isinstance(batch.get('tasks'),list) or len(batch['tasks'])>10000
            or any(not valid_string(batch.get(k)) for k in ('media_type','audio_format','speed_mode'))):
        raise ValueError('Invalid task history batch.')
    statuses={'queued','running','running_uninterruptible','completed','failed','cancelled'}
    for task in batch['tasks']:
        if (not isinstance(task,dict) or any(not valid_string(task.get(k)) for k in
                    ('id','url','media_type','audio_format','speed_mode'))
                or task.get('id') in task_ids or task.get('platform') not in {'youtube','instagram','bilibili','local'}
                or task.get('status') not in statuses or type(task.get('index')) is not int or task['index']<1
                or type(task.get('attempt_count')) is not int or task['attempt_count']<0
                or not isinstance(task.get('attempts'),list) or len(task['attempts'])>20
                or (task.get('download_dir') is not None and not isinstance(task['download_dir'],str))
                or (task.get('error') is not None and not isinstance(task['error'],dict))
                or (task.get('result') is not None and not isinstance(task['result'],dict))):
            raise ValueError('Invalid task history task.')
        task_ids.add(task['id'])
        for attempt in task['attempts']:
            if (not isinstance(attempt,dict) or attempt.get('status') not in statuses
                    or type(attempt.get('number')) is not int or attempt['number']<1
                    or not finite(attempt.get('started_at'))
                    or (attempt.get('finished_at') is not None and not finite(attempt['finished_at']))):
                raise ValueError('Invalid task history attempt.')

def stage_history_import(source, root):
    source = Path(source).resolve()
    if source.stat().st_size > MAX_HISTORY_BYTES:
        raise ValueError('History exceeds 64 MiB.')
    destination = Path(root) / 'task-history-import.sqlite3'
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.history-', dir=destination.parent)
    os.close(fd)
    try:
        with closing(sqlite3.connect(source.as_uri() + '?mode=ro', uri=True)) as original, closing(sqlite3.connect(temporary)) as snapshot:
            if original.execute('PRAGMA quick_check').fetchone() != ('ok',):
                raise ValueError('History database failed integrity validation.')
            columns = {row[1] for row in original.execute('PRAGMA table_info(task_batches)')}
            if columns != {'id','created_at','payload'}:
                raise ValueError('Incompatible task history database.')
            task_ids = set()
            for identifier, created, payload in original.execute('SELECT id, created_at, payload FROM task_batches'):
                batch = json.loads(payload)
                validate_history_batch(batch, identifier, created, task_ids)
            snapshot.execute('CREATE TABLE task_batches(id TEXT PRIMARY KEY, created_at REAL NOT NULL, payload TEXT NOT NULL)')
            snapshot.executemany('INSERT INTO task_batches VALUES (?,?,?)', original.execute('SELECT id, created_at, payload FROM task_batches'))
            snapshot.commit()
        os.chmod(temporary, 0o600)
        os.replace(temporary, destination)
    except (sqlite3.Error, json.JSONDecodeError) as error:
        raise ValueError('Invalid task history database.') from error
    finally:
        if os.path.exists(temporary): os.unlink(temporary)
    return destination

def apply_pending_history(root):
    """Apply a selected import before opening the live store; retain a backup."""
    root = Path(root)
    pending = root / 'task-history-import.sqlite3'
    if not pending.exists(): return False
    live = Path(os.environ.get('GTD_HISTORY_PATH', str(root / 'task_history.sqlite3')))
    # Revalidate the staged snapshot before touching the live store.
    validated = stage_history_import(pending, root)
    if live.exists(): atomic_write(live.with_suffix('.sqlite3.before-import'), read_bounded(live, MAX_HISTORY_BYTES))
    atomic_write(live, read_bounded(validated, MAX_HISTORY_BYTES))
    validated.unlink()
    return True
