"""Own one authenticated, loopback-only WSGI server for the desktop window."""
from __future__ import annotations

import hmac
import re
import threading

from werkzeug.serving import WSGIRequestHandler, make_server
from werkzeug.wrappers import Request, Response


class DesktopApplication:
    def __init__(self, app, token: str, port: int):
        self.app = app
        self.token = token
        self.host = f'127.0.0.1:{port}'
        self.origin = f'http://{self.host}'

    def __call__(self, environ, start_response):
        request = Request(environ)
        supplied = request.headers.get('X-GTD-Desktop-Token', '')
        origin = request.headers.get('Origin')
        if (request.host != self.host or not hmac.compare_digest(supplied.encode('utf-8'), self.token.encode('ascii'))
                or (origin and origin != self.origin)):
            return Response('{"error":"Desktop session required"}', status=403,
                            content_type='application/json')(environ, start_response)
        response = Response.from_app(self.app, environ)
        if response.mimetype == 'text/html' and response.status_code == 200:
            html = response.get_data(as_text=True)
            html = re.sub(r'<html(?=[\s>])', '<html data-desktop="true"', html, count=1)
            html = html.replace('</head>', '<link rel="stylesheet" href="/static/css/desktop.css"></head>', 1)
            response.set_data(html)
        return response(environ, start_response)


class QuietHandler(WSGIRequestHandler):
    def log_request(self, code='-', size='-'):
        # Tokens are headers, never URLs, and routine requests don't need logs.
        pass


class DesktopServer:
    def __init__(self, app, token: str, port: int = 18233):
        self.app, self.token, self.port = app, token, port
        self.server = None
        self.thread = None

    def start(self) -> str:
        try:
            self.server = make_server('127.0.0.1', self.port,
                                     DesktopApplication(self.app, self.token, self.port),
                                     threaded=True, request_handler=QuietHandler)
        except (OSError, SystemExit) as error:
            raise RuntimeError('GTD Desktop 已在运行或端口 18233 被占用。请关闭已有桌面实例后重试。\n'
                               'GTD Desktop is already running or port 18233 is busy. Close the existing desktop instance and retry.') from error
        self.thread = threading.Thread(target=self.server.serve_forever, name='gtd-desktop-server', daemon=True)
        self.thread.start()
        return f'http://127.0.0.1:{self.port}'

    def close(self):
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            self.thread.join(timeout=5)
            self.server = None


def stop_tasks(manager):
    for summary in manager.list_batches():
        for task in manager.snapshot(summary['id'])['tasks']:
            if task.get('can_cancel'):
                try:
                    manager.cancel(summary['id'], task['id'])
                except (KeyError, ValueError):
                    pass  # A task can finish between snapshot and cancellation.
    manager.shutdown(wait=True)


class DesktopInstanceLock:
    """OS advisory lock acquired before opening/importing the live task database."""
    def __init__(self, root):
        from pathlib import Path
        self.path = Path(root) / 'state/desktop.lock'
        self.handle = None

    def __enter__(self):
        import os
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = self.path.open('a+b')
        try:
            if os.name == 'nt':
                import msvcrt
                self.handle.seek(0, 2)
                if not self.handle.tell():
                    self.handle.write(b'0'); self.handle.flush()
                self.handle.seek(0)
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            self.handle.close(); self.handle = None
            raise RuntimeError('GTD Desktop is already running. / GTD 桌面版已在运行。') from error
        return self

    def __exit__(self, *args):
        import os
        if self.handle:
            if os.name == 'nt':
                import msvcrt
                self.handle.seek(0)
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
            self.handle.close(); self.handle = None
