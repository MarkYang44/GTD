"""HTTP adapter for local extraction; task lifecycle stays in TaskManager."""
from pathlib import Path

from flask import Blueprint, jsonify, render_template, request, send_file
from werkzeug.exceptions import RequestEntityTooLarge

from download_errors import DownloadFailure, public_error
from local_audio import MAX_FILE_BYTES
from task_control import TaskSeed


def with_download_links(batch):
    for task in batch.get('tasks', []):
        if task.get('platform') == 'local' and task.get('status') == 'completed' and (task.get('result') or {}).get('local_extraction'):
            task['result']['download_url'] = f'/api/extract-audio/{batch["id"]}/{task["id"]}/file'
    return batch


def extraction_blueprint(manager, store, output_dir=None):
    bp = Blueprint('audio_extract', __name__)

    def cleanup():
        manager.cleanup_inputs('local', store.cleanup)

    @bp.get('/extract-audio')
    def page():
        return render_template('extract_audio.html')

    @bp.post('/api/extract-audio')
    def upload():
        request.max_content_length = MAX_FILE_BYTES + 1024**2
        request.max_form_memory_size = 1024 * 1024
        request.max_form_parts = 8
        key = None
        try:
            mode = request.form.get('audio_format', 'source')
            files = request.files.getlist('video')
            if mode not in {'source', 'mp3'} or len(files) != 1 or len(request.files) != 1:
                return jsonify(error_code='INVALID_UPLOAD', message='请选择一个视频和有效音频格式'), 400
            cleanup()
            key = store.save(files[0])
            _, name = store.resolve(key)
            batch = manager.create_batch([TaskSeed('local', key, title=name)], 'audio', mode, 'standard', output_dir)
            return jsonify(batch_id=batch['id'], task_count=batch['total']), 202
        except RequestEntityTooLarge:
            return jsonify(error_code='UPLOAD_TOO_LARGE', message='视频文件不能超过 2 GiB'), 413
        except DownloadFailure as error:
            if key:
                store.remove(key)
            status = 413 if error.info.error_code == 'UPLOAD_TOO_LARGE' else 507 if error.info.error_code == 'UPLOAD_STORAGE_FULL' else 400
            return jsonify(public_error(error)), status
        except (OSError, ValueError):
            if key:
                store.remove(key)
            return jsonify(error_code='UPLOAD_STORAGE_FULL', message='无法保存视频或创建输出目录'), 507

    @bp.get('/api/extract-audio/batches')
    def history():
        cleanup()
        batches = []
        for summary in manager.list_batches():
            try:
                snapshot = manager.snapshot(summary['id'])
            except KeyError:
                continue
            if snapshot['tasks'] and all(t['platform'] == 'local' for t in snapshot['tasks']):
                batches.append(summary)
        return jsonify(batches=batches)

    @bp.get('/api/extract-audio/<batch_id>/<task_id>/file')
    def output(batch_id, task_id):
        try:
            batch = manager.snapshot(batch_id)
            task = next(t for t in batch['tasks'] if t['id'] == task_id)
            result = task.get('result') or {}
            if task['platform'] != 'local' or task['status'] != 'completed' or not result.get('local_extraction'):
                raise ValueError('Not an extraction result')
            path = Path(result['filepath'])
            directory = Path(batch['download_dir']).resolve()
            if path.is_symlink() or path.resolve().parent != directory or not path.is_file():
                raise ValueError('Output unavailable')
            return send_file(path, as_attachment=True, conditional=True)
        except (KeyError, StopIteration, ValueError, OSError):
            return jsonify(error_code='OUTPUT_NOT_FOUND', message='输出文件不存在或已被移动'), 404

    return bp
