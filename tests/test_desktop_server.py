import unittest
from flask import Flask
from werkzeug.test import Client
from werkzeug.wrappers import Response


class DesktopServerTests(unittest.TestCase):
    def setUp(self):
        from desktop_server import DesktopApplication
        app=Flask(__name__)
        app.add_url_rule('/',endpoint='home',view_func=lambda:'<html><head></head><body>original</body></html>')
        app.add_url_rule('/api/write',endpoint='write',view_func=lambda:'ok',methods=['POST'])
        self.client=Client(DesktopApplication(app,'test-secret',18233),Response)
        self.headers={'Host':'127.0.0.1:18233','X-GTD-Desktop-Token':'test-secret'}

    def test_unauthorized_and_hostile_requests_are_rejected(self):
        self.assertEqual(self.client.get('/',headers={'Host':'127.0.0.1:18233'}).status_code,403)
        for changes in [{'Host':'evil.test'},{'X-GTD-Desktop-Token':'wrong'}, {'X-GTD-Desktop-Token':'非法'},{'Origin':'https://evil.test'}]:
            headers={**self.headers,**changes}
            self.assertEqual(self.client.post('/api/write',headers=headers).status_code,403)

    def test_original_routes_and_desktop_style_are_preserved(self):
        response=self.client.get('/',headers=self.headers)
        self.assertEqual(response.status_code,200)
        self.assertIn(b'original',response.data)
        self.assertIn(b'/static/css/desktop.css',response.data)
        self.assertIn(b'data-desktop',response.data)
        self.assertEqual(self.client.post('/api/write',headers={**self.headers,'Origin':'http://127.0.0.1:18233'}).data,b'ok')

    def test_binary_results_are_not_materialized_or_modified(self):
        from desktop_server import DesktopApplication
        def app(environ,start_response):
            start_response('200 OK',[('Content-Type','application/octet-stream')])
            return iter([b'ab',b'cd'])
        response=Client(DesktopApplication(app,'test-secret',18233),Response).get('/',headers=self.headers)
        self.assertEqual(response.data,b'abcd')

class DesktopInstanceTests(unittest.TestCase):
    def test_second_instance_is_rejected_until_first_releases_lock(self):
        import tempfile
        from pathlib import Path
        from desktop_server import DesktopInstanceLock
        with tempfile.TemporaryDirectory() as tmp:
            first = DesktopInstanceLock(Path(tmp))
            with first:
                with self.assertRaisesRegex(RuntimeError, 'already running'):
                    with DesktopInstanceLock(Path(tmp)):
                        self.fail('A second process could import pending history')
            with DesktopInstanceLock(Path(tmp)):
                pass
