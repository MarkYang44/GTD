import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class DesktopPathsTests(unittest.TestCase):
    def test_source_paths_remain_in_repository(self):
        import gtd_paths
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(gtd_paths.runtime_root(), gtd_paths.resource_root())
            self.assertEqual(gtd_paths.downloads_root(), gtd_paths.resource_root() / 'downloads')

    def test_desktop_user_paths_are_platform_specific(self):
        import gtd_paths
        self.assertEqual(gtd_paths.user_data_root('darwin', Path('/user'), {}), Path('/user/Library/Application Support/GTD'))
        self.assertEqual(gtd_paths.user_data_root('win32', Path('/user'), {'LOCALAPPDATA':'C:/Local'}), Path('C:/Local/GTD'))

    def test_initialization_preserves_edited_calendar_and_uses_private_tool_path(self):
        import gtd_paths
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {}, clear=True), patch.object(Path, 'home', return_value=Path(tmp).resolve()):
            root=Path(tmp).resolve()
            initialized=gtd_paths.initialize_desktop(root)
            current=root/'data/lmu/calendar/current.json'
            self.assertEqual(initialized, root)
            self.assertTrue(current.exists())
            current.write_text('user maintained calendar')
            gtd_paths.initialize_desktop(root)
            self.assertEqual(current.read_text(), 'user maintained calendar')
            self.assertEqual(gtd_paths.runtime_root(),root)
            self.assertNotEqual(gtd_paths.downloads_root(),gtd_paths.resource_root()/'downloads')
            self.assertEqual(Path(os.environ['GTD_HISTORY_PATH']),root/'state/tasks.sqlite3')
            self.assertEqual(os.environ['PATH'].split(os.pathsep)[0],str(gtd_paths.resource_root()/'tools/desktop-bin/bin'))
