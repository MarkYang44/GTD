#!/usr/bin/env python3
"""Launch GTD as a desktop application without a user-managed Python server."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import tempfile


def self_test(app_module, root: Path) -> dict:
    """Exercise shipped resources and real media processing without a GUI/network."""
    from desktop_server import DesktopApplication
    from werkzeug.test import Client
    from werkzeug.wrappers import Response
    token = secrets.token_hex(32)
    client = Client(DesktopApplication(app_module.app, token, 18233), Response)
    headers = {'Host': '127.0.0.1:18233', 'X-GTD-Desktop-Token': token}
    routes = ['/', '/guide', '/extract-audio', '/kozekilmu', '/kozekilmu/tracks',
              '/kozekilmu/cars', '/kozekilmu/strategy', '/kozekilmu/calendar', '/kozekilmu/updates']
    for route in routes:
        response = client.get(route, headers=headers)
        if response.status_code != 200 or b'data-desktop' not in response.data:
            raise RuntimeError(f'Resource check failed: {route} ({response.status_code})')
        response.close()
    tools = {}
    for tool in ('ffmpeg', 'ffprobe', 'aria2c', 'node'):
        executable = shutil.which(tool)
        if not executable:
            raise RuntimeError(f'Missing bundled runtime: {tool}')
        result = subprocess.run([executable, '-version' if tool in ('ffmpeg','ffprobe') else '--version'],
                                capture_output=True, text=True, timeout=30, check=True)
        tools[tool] = {'path': executable, 'version': (result.stdout or result.stderr).splitlines()[0]}
    # Send a real MP4 through the original upload/queue/FFmpeg/result-download API.
    with tempfile.TemporaryDirectory(prefix='gtd-self-test-', dir=root / 'state') as tmp:
        video = Path(tmp) / 'sample.mp4'
        output = Path(tmp) / 'out'
        subprocess.run([tools['ffmpeg']['path'], '-v', 'error', '-f', 'lavfi', '-i',
                        'color=s=32x32:d=0.3', '-f', 'lavfi', '-i', 'sine=frequency=440:duration=0.3',
                        '-c:v', 'mpeg4', '-c:a', 'aac', '-shortest', str(video)], check=True, timeout=30)
        with video.open('rb') as source:
            response = client.post('/api/extract-audio', headers=headers,
                                   data={'video': (source, 'sample.mp4'), 'audio_format': 'mp3', 'output_dir': str(output)})
        if response.status_code != 202:
            raise RuntimeError(f'Upload failed: {response.status_code} {response.get_data(as_text=True)}')
        batch_id = response.json['batch_id']
        if not app_module.task_manager.wait_for_idle(timeout=30):
            raise RuntimeError('Media self-test timed out')
        batch = app_module.task_manager.snapshot(batch_id)
        task = batch['tasks'][0]
        if task['status'] != 'completed':
            raise RuntimeError(f'Media self-test failed: {task.get("error")}')
        result_path = Path(task['result']['filepath'])
        subprocess.run([tools['ffprobe']['path'], '-v', 'error', str(result_path)], check=True, timeout=15)
        download_url = f'/api/extract-audio/{batch_id}/{task["id"]}/file'
        result_response = client.get(download_url, headers=headers)
        if result_response.status_code != 200 or result_response.data != result_path.read_bytes():
            raise RuntimeError('Result transfer failed')
        result_response.close()
    return {'ok': True, 'routes': routes, 'tools': tools, 'media': 'MP4 upload → MP3 extraction → result transfer'}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='GTD Desktop')
    parser.add_argument('--self-test', action='store_true', help='Check resources and bundled media tools without opening a window')
    parser.add_argument('--report', type=Path, help='Save the self-test JSON report')
    args = parser.parse_args(argv)
    from gtd_paths import initialize_desktop
    root = initialize_desktop()
    if args.self_test:
        os.environ['GTD_DOWNLOAD_DIR'] = str(root / 'state/self-test-output')
    from desktop_server import DesktopInstanceLock
    with DesktopInstanceLock(root):
        return run_desktop(args, root)


def run_desktop(args, root):
    from desktop_settings import apply_pending_history
    apply_pending_history(root)
    import app as app_module
    from desktop_server import DesktopServer, stop_tasks
    server = None
    try:
        if args.self_test:
            report = self_test(app_module, root)
            if args.report:
                args.report.parent.mkdir(parents=True, exist_ok=True)
                args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
            if sys.stdout:
                print(json.dumps(report, ensure_ascii=False, indent=2))
            return 0
        from desktop_window import run_window
        token = secrets.token_hex(32)
        server = DesktopServer(app_module.app, token)
        url = server.start()
        return run_window(url, token, root, app_module)
    finally:
        if server:
            server.close()
        stop_tasks(app_module.task_manager)


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as error:
        import traceback
        from gtd_paths import runtime_root
        root = runtime_root()
        (root / 'logs').mkdir(parents=True, exist_ok=True)
        (root / 'logs/desktop-startup.log').write_text(traceback.format_exc(), encoding='utf-8')
        if '--self-test' in sys.argv:
            if sys.stderr:
                print(str(error), file=sys.stderr)
            raise SystemExit(1)
        try:
            from PySide6.QtWidgets import QApplication, QMessageBox
            application = QApplication.instance() or QApplication(sys.argv[:1])
            QMessageBox.critical(None, 'GTD — Startup error', f'{error}\n\nLog: {root / "logs/desktop-startup.log"}')
        except Exception:
            if sys.stderr:
                print(str(error), file=sys.stderr)
        raise SystemExit(1)
