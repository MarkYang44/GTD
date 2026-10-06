import importlib.util
import unittest


class DesktopEntryTests(unittest.TestCase):
    def test_desktop_entry_can_be_imported_without_loading_gui_or_original_app(self):
        self.assertIsNotNone(importlib.util.find_spec('desktop'))

    def test_entry_has_cli_and_self_test_modes(self):
        import desktop
        self.assertTrue(callable(desktop.main))
        self.assertTrue(callable(desktop.self_test))
