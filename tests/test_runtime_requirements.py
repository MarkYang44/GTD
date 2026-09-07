import subprocess
import sys
import unittest

from runtime_requirements import require_supported_python


class RuntimeRequirementsTests(unittest.TestCase):
    def test_rejects_old_python_with_upgrade_instructions(self):
        for version in ((3, 8, 20), (3, 9, 24)):
            with self.subTest(version=version), self.assertRaises(SystemExit) as error:
                require_supported_python(version)
            message = str(error.exception)
            self.assertIn("Python 3.10+", message)
            self.assertIn("升级", message)
            self.assertIn("Upgrade", message)
            self.assertIn("{}.{}".format(*version), message)

    def test_accepts_minimum_and_newer_python(self):
        for version in ((3, 10, 0), (3, 13, 0), (3, 14, 0)):
            with self.subTest(version=version):
                self.assertIsNone(require_supported_python(version))

    def test_entrypoints_reject_old_python_before_importing_dependencies(self):
        for entrypoint in ("main.py", "app.py"):
            with self.subTest(entrypoint=entrypoint):
                script = (
                    "import runpy, sys; "
                    "sys.version_info = (3, 9, 0); "
                    "sys.modules['yt_dlp'] = None; "
                    "sys.modules['flask'] = None; "
                    "runpy.run_path({!r}, run_name='__main__')".format(entrypoint)
                )
                result = subprocess.run(
                    [sys.executable, "-c", script], capture_output=True, text=True,
                    encoding="utf-8",
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("Python 3.10+", result.stderr)
                self.assertNotIn("ModuleNotFoundError", result.stderr)


if __name__ == "__main__":
    unittest.main()
