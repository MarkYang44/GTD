import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
import desktop_settings as settings

class DesktopSettingsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
    def test_cookie_validation_preserves_existing(self):
        source = self.root / 'source.txt'
        target = self.root / 'youtube_cookies.txt'
        target.write_text('existing')
        source.write_text('not cookies')
        with self.assertRaises(ValueError): settings.import_cookies(source, self.root, 'youtube')
        self.assertEqual(target.read_text(), 'existing')
        source.write_text('# Netscape HTTP Cookie File\n.youtube.com\tTRUE\t/\tTRUE\t0\tSID\tsecret\n')
        self.assertEqual(settings.import_cookies(source, self.root, 'youtube'), target)
    def test_unknown_platform_rejected(self):
        with self.assertRaises(ValueError): settings.import_cookies(self.root / 'x', self.root, '../escape')
    def test_favorites_exact_shape_and_strings(self):
        self.assertEqual(settings.validate_favorites({'circuits':['spa','spa'], 'cars':[]}), {'circuits':['spa'], 'cars':[]})
        for value in ({'circuits':[]}, {'circuits':[1],'cars':[]}, {'circuits':[],'cars':[],'extra':1}):
            with self.assertRaises(ValueError): settings.validate_favorites(value)
    def test_history_staged_does_not_replace_live(self):
        source = self.root / 'source.sqlite3'
        with closing(sqlite3.connect(source)) as db:
            db.execute('CREATE TABLE task_batches(id TEXT PRIMARY KEY, created_at REAL NOT NULL, payload TEXT NOT NULL)')
            db.execute('INSERT INTO task_batches VALUES (?,?,?)', ('batch', 1, json.dumps({'id':'batch','created_at':1,'media_type':'video','audio_format':'mp3','speed_mode':'standard','tasks':[]})))
            db.commit()
        live = self.root / 'task_history.sqlite3'
        live.write_bytes(b'live')
        staged = settings.stage_history_import(source, self.root)
        self.assertEqual(live.read_bytes(), b'live')
        self.assertEqual(staged.name, 'task-history-import.sqlite3')
        with closing(sqlite3.connect(staged)) as db: self.assertEqual(db.execute('SELECT count(*) FROM task_batches').fetchone()[0], 1)
    def test_bad_history_rejected(self):
        source = self.root / 'bad.sqlite3'
        with closing(sqlite3.connect(source)) as db: db.execute('CREATE TABLE bad(x)')
        with self.assertRaises(ValueError): settings.stage_history_import(source, self.root)
    def test_invalid_calendar_preserves_publication(self):
        source = self.root / 'bad.json'; source.write_text('{}')
        with self.assertRaises(ValueError): settings.import_calendar(source, self.root)
        self.assertFalse((self.root / 'data/lmu/calendar/current.json').exists())

    def test_history_rejects_invalid_task_payload(self):
        source = self.root / 'invalid.sqlite3'
        with closing(sqlite3.connect(source)) as db:
            db.execute('CREATE TABLE task_batches(id TEXT PRIMARY KEY, created_at REAL NOT NULL, payload TEXT NOT NULL)')
            db.execute('INSERT INTO task_batches VALUES (?,?,?)', ('b',1,json.dumps({'id':'b','created_at':1,'tasks':[{}]})))
            db.commit()
        with self.assertRaises(ValueError): settings.stage_history_import(source,self.root)

    def test_pending_import_keeps_backup(self):
        import os
        from unittest.mock import patch
        source = self.root / 'source.sqlite3'
        with closing(sqlite3.connect(source)) as db:
            db.execute('CREATE TABLE task_batches(id TEXT PRIMARY KEY, created_at REAL NOT NULL, payload TEXT NOT NULL)')
            db.commit()
        settings.stage_history_import(source,self.root)
        live = self.root / 'state/tasks.sqlite3'; live.parent.mkdir(); live.write_bytes(b'old history')
        with patch.dict(os.environ, {'GTD_HISTORY_PATH':str(live)}):
            self.assertTrue(settings.apply_pending_history(self.root))
        self.assertEqual(live.with_suffix('.sqlite3.before-import').read_bytes(),b'old history')
        self.assertFalse((self.root/'task-history-import.sqlite3').exists())
        with closing(sqlite3.connect(live)) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM task_batches').fetchone()[0],0)

    def test_history_rejects_missing_payload_creation_time(self):
        source = self.root / 'missing-time.sqlite3'
        with closing(sqlite3.connect(source)) as db:
            db.execute('CREATE TABLE task_batches(id TEXT PRIMARY KEY, created_at REAL NOT NULL, payload TEXT NOT NULL)')
            db.execute('INSERT INTO task_batches VALUES (?,?,?)', ('b',1,json.dumps({'id':'b','media_type':'video','audio_format':'mp3','speed_mode':'normal','tasks':[]})))
            db.commit()
        with self.assertRaises(ValueError): settings.stage_history_import(source,self.root)

    def test_real_history_stages_and_restores(self):
        from task_control import TaskManager, TaskSeed
        from task_history import TaskHistoryStore
        store=TaskHistoryStore(self.root/'real.sqlite3')
        manager=TaskManager(lambda url,**kw:{'filepath':str(self.root/'result.mp4')},history_store=store)
        try:
            batch=manager.create_batch([TaskSeed('youtube','https://example.com/video')],'video','mp3','normal',str(self.root/'media'))
            self.assertTrue(manager.wait_for_idle())
        finally:manager.shutdown()
        staged=settings.stage_history_import(store.path,self.root)
        restored=TaskManager(lambda url,**kw:None,history_store=TaskHistoryStore(staged))
        try:self.assertEqual(restored.snapshot(batch['id'])['completed'],1)
        finally:restored.shutdown()

    def test_cookie_bom_import_loads_with_actual_consumer(self):
        from http.cookiejar import MozillaCookieJar
        source=self.root/'bom.txt'
        source.write_text('# Netscape HTTP Cookie File\n#HttpOnly_.youtube.com\tTRUE\t/\tTRUE\t0\tSID\tsecret\n',encoding='utf-8-sig')
        target=settings.import_cookies(source,self.root,'youtube')
        jar=MozillaCookieJar(str(target));jar.load(ignore_discard=True,ignore_expires=True)
        self.assertEqual(len(jar),1)

    def test_cookie_header_required(self):
        source=self.root/'noheader.txt'
        source.write_text('.youtube.com\tTRUE\t/\tTRUE\t0\tSID\tsecret\n')
        with self.assertRaises(ValueError):settings.import_cookies(source,self.root,'youtube')

    def test_history_rejects_restore_hazards(self):
        from task_control import TaskManager, TaskSeed
        from task_history import TaskHistoryStore
        store=TaskHistoryStore(self.root/'hazards.sqlite3')
        manager=TaskManager(lambda url,**kw:{'filepath':str(self.root/'result.mp4')},history_store=store)
        try:
            manager.create_batch([TaskSeed('youtube','https://example.com/video')],'video','mp3','normal',str(self.root/'media'))
            self.assertTrue(manager.wait_for_idle())
        finally:manager.shutdown()
        original=store.load_batches()[0]
        from copy import deepcopy
        cases=[]
        bad=deepcopy(original);bad['created_at']=float('nan');cases.append(bad)
        bad=deepcopy(original);bad['tasks'].append(deepcopy(bad['tasks'][0]));cases.append(bad)
        bad=deepcopy(original);bad['tasks'][0]['status']='unknown';cases.append(bad)
        bad=deepcopy(original);del bad['tasks'][0]['attempts'][0]['status'];cases.append(bad)
        for value in cases:
            with self.subTest(value=value):
                with closing(sqlite3.connect(store.path)) as db:
                    db.execute('UPDATE task_batches SET payload=?',(json.dumps(value),));db.commit()
                with self.assertRaises(ValueError):settings.stage_history_import(store.path,self.root)

    def test_redownload_history_over_initial_task_cap_is_accepted(self):
        from task_control import TaskManager, TaskSeed
        from task_history import TaskHistoryStore
        store=TaskHistoryStore(self.root/'large-real.sqlite3')
        manager=TaskManager(lambda url,**kw:{'filepath':str(self.root/'result.mp4')},history_store=store)
        try:
            batch=manager.create_batch([TaskSeed('youtube',f'https://example.com/{i}') for i in range(100)],'video','mp3','normal',str(self.root/'media'))
            self.assertTrue(manager.wait_for_idle(10))
            manager.redownload(batch['id'],batch['tasks'][0]['id'])
            self.assertTrue(manager.wait_for_idle(10))
        finally:manager.shutdown()
        self.assertEqual(len(store.load_batches()[0]['tasks']),101)
        staged=settings.stage_history_import(store.path,self.root)
        self.assertTrue(staged.exists())

    def test_native_picker_capability_replaces_unavailable_os_backend(self):
        from types import SimpleNamespace
        from desktop_window import install_native_folder_picker
        module=SimpleNamespace(choose_folder=lambda initial:None,folder_picker_available=lambda:False)
        picker=lambda initial:'/native/selection'
        install_native_folder_picker(module,picker)
        self.assertTrue(module.folder_picker_available())
        self.assertEqual(module.choose_folder('/initial'),'/native/selection')
