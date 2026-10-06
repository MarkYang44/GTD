import tempfile
import unittest
from pathlib import Path
from scripts.build_desktop import public_resources, validate_tools

class DesktopBuildTests(unittest.TestCase):
    def test_resource_allowlist_does_not_include_private_state(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            allowed = ['templates/index.html', 'static/js/app.js', 'assets/fallback_covers/default.png', 'data/lmu/releases.json', 'data/lmu/2026.09.22.1.json', 'data/lmu/calendar/current.json', 'data/lmu/calendar/schema.json', 'docs/WEB_GUIDE.md']
            private = ['cookies.txt', 'downloads/a.mp4', 'data/history.sqlite', 'data/lmu/calendar/status.json', 'data/lmu/calendar/previous.json', 'data/lmu/calendar/imports/a.json', 'data/lmu/calendar/current.json.lock', 'static/.DS_Store', 'static/secrets.py', 'venv/key.txt', '.git/config']
            for name in allowed + private:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('fixture')
            actual = {source.relative_to(root).as_posix() for source, destination in public_resources(root)}
            self.assertEqual(actual, set(allowed))
    def test_tools_required(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(RuntimeError, 'ffmpeg'):
                validate_tools(Path(directory), windows=False)

class DesktopRealManifestTests(unittest.TestCase):
    def test_actual_release_snapshots_and_web_manifest_are_bundled(self):
        import json
        root = Path(__file__).resolve().parents[1]
        resources = {source.relative_to(root).as_posix() for source, _ in public_resources(root)}
        for release in json.loads((root / 'data/lmu/releases.json').read_text(encoding='utf-8')):
            self.assertIn('data/lmu/' + release['snapshot'], resources)
        self.assertIn('static/site.webmanifest', resources)

if __name__ == '__main__':
    unittest.main()
