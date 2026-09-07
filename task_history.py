"""Small SQLite repository for restart-safe local download history.

Only explicitly selected task metadata is stored: credentials, downloader
internals, progress events, and private error diagnostics never enter history.
Connections are short lived so the store works across executor threads.
"""
from __future__ import annotations

import json
from contextlib import contextmanager
import sqlite3
from pathlib import Path


_BATCH_FIELDS = ('id', 'created_at', 'media_type', 'audio_format', 'speed_mode', 'download_dir')
_TASK_FIELDS = (
    'id', 'index', 'platform', 'url', 'title', 'position', 'media_type',
    'audio_format', 'speed_mode', 'download_dir', 'speed_mode_used',
    'turbo_fallback', 'output_version', 'version_key', 'base_filepath',
    'status', 'attempt_count',
)
_RESULT_FIELDS = (
    'platform', 'title', 'filepath', 'filesize', 'media_type',
    'speed_mode_requested', 'speed_mode_used', 'turbo_fallback',
    'output_version_actual', 'cover_embedded', 'cover_source', 'fallback_cover',
    'format', 'acodec', 'audio_format_requested', 'audio_format_used',
    'audio_format_fallback', 'output_ext', 'source_acodec', 'source_abr_kbps',
    'resolution', 'fps', 'vcodec',
)
_ERROR_FIELDS = ('error_code', 'message', 'suggestion', 'retryable')
_ATTEMPT_FIELDS = ('number', 'status', 'started_at', 'finished_at', 'output_version')


def _select(value: dict, fields: tuple[str, ...]) -> dict:
    return {key: value[key] for key in fields if key in value
            and isinstance(value[key], (str, int, float, bool, type(None)))}


def _safe_batch(batch: dict) -> dict:
    saved = _select(batch, _BATCH_FIELDS)
    saved['tasks'] = []
    for task in batch['tasks']:
        item = _select(task, _TASK_FIELDS)
        item['error'] = _select(task['error'], _ERROR_FIELDS) if isinstance(task.get('error'), dict) else None
        item['result'] = _select(task['result'], _RESULT_FIELDS) if isinstance(task.get('result'), dict) else None
        item['attempts'] = []
        for attempt in task.get('attempts', [])[-20:]:
            entry = _select(attempt, _ATTEMPT_FIELDS)
            entry['error'] = _select(attempt['error'], _ERROR_FIELDS) if isinstance(attempt.get('error'), dict) else None
            item['attempts'].append(entry)
        saved['tasks'].append(item)
    return saved


class TaskHistoryStore:
    """Persist one batch per transaction; pruning is controlled by TaskManager."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as connection:
            connection.execute('CREATE TABLE IF NOT EXISTS task_batches ('
                               'id TEXT PRIMARY KEY, created_at REAL NOT NULL, payload TEXT NOT NULL)')

    @contextmanager
    def _connection(self):
        connection = sqlite3.connect(self.path, timeout=10)
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def save_batch(self, batch: dict) -> None:
        saved = _safe_batch(batch)
        payload = json.dumps(saved, ensure_ascii=False, allow_nan=False)
        with self._connection() as connection:
            connection.execute('INSERT INTO task_batches (id, created_at, payload) VALUES (?, ?, ?) '
                               'ON CONFLICT(id) DO UPDATE SET payload = excluded.payload, created_at = excluded.created_at',
                               (saved['id'], saved['created_at'], payload))

    def load_batches(self) -> list[dict]:
        with self._connection() as connection:
            rows = connection.execute('SELECT payload FROM task_batches ORDER BY created_at, rowid').fetchall()
        return [json.loads(row[0]) for row in rows]

    def delete_batch(self, batch_id: str) -> None:
        with self._connection() as connection:
            connection.execute('DELETE FROM task_batches WHERE id = ?', (batch_id,))
