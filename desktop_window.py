"""Native Qt shell. Web functions continue to use the original local Flask app."""
import json
import threading
from pathlib import Path
from urllib.parse import urlsplit
from desktop_settings import (import_cookies, import_calendar, stage_history_import,
                              validate_favorites, read_bounded, atomic_write)

NAVIGATION = [('/', '下载中心', 'Downloads'), ('/extract-audio', '本地音频', 'Local audio'),
              ('/kozekilmu/tracks', 'LMU 指南', 'LMU guide'), ('/kozekilmu', '冠军档案', 'Champions'),
              ('/kozekilmu/cars', '车型图鉴', 'Car catalog'), ('/kozekilmu/strategy', '燃油与进站', 'Fuel & pit stops'),
              ('/kozekilmu/calendar', '每周赛历', 'Weekly calendar'), ('/kozekilmu/updates', '内容更新', 'Updates'),
              ('/#task-card', '任务', 'Tasks'), ('/guide', '使用说明', 'Help')]

def install_native_folder_picker(app_module, picker):
    """Qt owns desktop picking, independent of optional OS scripting tools."""
    app_module.choose_folder = picker
    app_module.folder_picker_available = lambda: True

def run_window(base_url: str, token: str, data_root: Path, app_module) -> int:
    from PySide6.QtCore import QObject, Signal, Slot, Qt, QUrl, QTimer
    from PySide6.QtGui import QDesktopServices, QIcon
    from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
                                  QPushButton, QLabel, QFileDialog, QMessageBox, QDialog)
    from PySide6.QtWebEngineCore import QWebEngineProfile, QWebEnginePage, QWebEngineUrlRequestInterceptor
    from PySide6.QtWebEngineWidgets import QWebEngineView
    root = Path(data_root)
    origin = urlsplit(base_url)
    def local(url):
        candidate = urlsplit(url.toString())
        return (candidate.scheme, candidate.hostname, candidate.port) == (origin.scheme, origin.hostname, origin.port)
    class Interceptor(QWebEngineUrlRequestInterceptor):
        def interceptRequest(self, info):
            if local(info.requestUrl()): info.setHttpHeader(b'X-GTD-Desktop-Token', token.encode('ascii'))
    class Page(QWebEnginePage):
        def acceptNavigationRequest(self, url, kind, main):
            if local(url): return True
            if url.scheme() == 'blob' and url.toString().startswith('blob:' + base_url + '/'): return True
            if url.scheme() == 'about' and not main: return True
            if main and url.scheme() in ('http','https'): QDesktopServices.openUrl(url)
            return False
        def createWindow(self, kind):
            page = Page(self.profile(), self)
            # Popup pages use the same navigation guard and cannot reveal the token.
            return page
    class FolderBridge(QObject):
        request = Signal(object)
        def __init__(self, owner):
            super().__init__(owner); self.owner = owner
            self.request.connect(self.select, Qt.ConnectionType.QueuedConnection)
        @Slot(object)
        def select(self, request):
            try: request['value'] = QFileDialog.getExistingDirectory(self.owner, self.owner.tr('选择文件夹','Choose folder'), str(request['initial']))
            finally: request['event'].set()
        def choose(self, initial):
            if threading.current_thread() is threading.main_thread():
                return QFileDialog.getExistingDirectory(self.owner, self.owner.tr('选择文件夹','Choose folder'), str(initial)) or None
            request = {'initial': initial, 'event': threading.Event(), 'value': ''}
            self.request.emit(request)
            while not request['event'].wait(.2):
                if self.owner.closing: return None
            return request['value'] or None
    class Window(QMainWindow):
        def __init__(self):
            super().__init__(); self.language = 'zh'; self.theme = 'dark'; self.closing = False
            self.resize(1400, 940); self.setMinimumSize(900, 650); self.setWindowTitle('GTD · Designed by Mark Yang')
            from gtd_paths import resource_root
            icon = resource_root() / 'static/icons/favicon-64x64.png'
            if icon.exists(): self.setWindowIcon(QIcon(str(icon)))
            profile_dir = root / 'browser-profile'; profile_dir.mkdir(parents=True, exist_ok=True)
            self.profile = QWebEngineProfile('GTD', self)
            self.profile.setPersistentStoragePath(str(profile_dir)); self.profile.setCachePath(str(profile_dir / 'cache'))
            self.profile.setPersistentCookiesPolicy(QWebEngineProfile.PersistentCookiesPolicy.AllowPersistentCookies)
            self.interceptor = Interceptor(self.profile); self.profile.setUrlRequestInterceptor(self.interceptor)
            self.view = QWebEngineView(self); self.page = Page(self.profile, self.view); self.view.setPage(self.page)
            self.profile.downloadRequested.connect(self.save_download)
            main = QWidget(); layout = QHBoxLayout(main); layout.setContentsMargins(0,0,0,0); layout.setSpacing(0)
            sidebar = QWidget(); sidebar.setObjectName('sidebar'); sidebar.setFixedWidth(220); side = QVBoxLayout(sidebar)
            brand = QLabel('GTD'); brand.setObjectName('brand'); side.addWidget(brand)
            self.buttons = []
            for route, zh, en in NAVIGATION:
                button = QPushButton(zh); button.clicked.connect(lambda checked=False, route=route: self.view.setUrl(QUrl(base_url + route)))
                side.addWidget(button); self.buttons.append((button,zh,en))
            side.addStretch(); self.theme_button = QPushButton(); self.theme_button.clicked.connect(self.toggle_theme); side.addWidget(self.theme_button)
            self.language_button = QPushButton('中文 / English'); self.language_button.clicked.connect(self.toggle_language); side.addWidget(self.language_button)
            self.settings_button = QPushButton(); self.settings_button.clicked.connect(self.settings); side.addWidget(self.settings_button)
            side.addWidget(QLabel('Designed by Mark Yang'))
            layout.addWidget(sidebar); layout.addWidget(self.view, 1); self.setCentralWidget(main)
            self.bridge = FolderBridge(self); install_native_folder_picker(app_module, self.bridge.choose)
            self.view.loadFinished.connect(lambda ok: self.sync_preferences())
            self.timer = QTimer(self); self.timer.timeout.connect(self.sync_preferences); self.timer.start(800)
            self.paint(); self.view.setUrl(QUrl(base_url + '/'))
        def tr(self, zh, en): return en if self.language == 'en' else zh
        def paint(self):
            for button,zh,en in self.buttons: button.setText(self.tr(zh,en))
            self.theme_button.setText(self.tr('切换主题','Switch theme')); self.settings_button.setText(self.tr('设置','Settings'))
            light = self.theme == 'light'; bg = '#eeece5' if light else '#242522'; fg = '#252623' if light else '#efeee7'
            self.setStyleSheet(f'QWidget {{background:{bg}; color:{fg}; font-size:13px;}} #sidebar {{border-right:1px solid #77786a;}} #brand {{font-size:32px;font-weight:800;color:#bfd754;padding:18px;}} QPushButton {{text-align:left;padding:11px;border:0;border-bottom:1px solid #55564d;}} QPushButton:hover {{background:#68733b;}} QPushButton:focus {{border:1px solid #bfd754;}}')
        def sync_preferences(self):
            if not local(self.view.url()): return
            self.page.runJavaScript("JSON.stringify([localStorage.getItem('gtd_theme_v1'), localStorage.getItem('gtd_language_v1')])", self.receive_preferences)
        def receive_preferences(self, values):
            if isinstance(values,str):
                try: values=json.loads(values)
                except ValueError:return
            if not isinstance(values,list) or len(values)!=2: return
            theme = 'light' if values[0]=='light' else 'dark'; language = 'en' if values[1]=='en' else 'zh'
            if (theme,language)!=(self.theme,self.language): self.theme,self.language=theme,language; self.paint()
        def preference(self,key,value):
            self.page.runJavaScript('localStorage.setItem('+json.dumps(key)+','+json.dumps(value)+');'); self.view.reload()
        def toggle_theme(self): self.preference('gtd_theme_v1', 'light' if self.theme=='dark' else 'dark')
        def toggle_language(self): self.preference('gtd_language_v1', 'en' if self.language=='zh' else 'zh')
        def save_download(self, download):
            from gtd_paths import downloads_root
            name = Path(download.suggestedFileName()).name or 'download'
            target,_ = QFileDialog.getSaveFileName(self,self.tr('保存下载结果','Save result'),str(downloads_root()/name))
            if not target: download.cancel(); return
            path = Path(target); download.setDownloadDirectory(str(path.parent)); download.setDownloadFileName(path.name); download.accept()
        def settings(self):
            dialog = QDialog(self); dialog.setWindowTitle(self.tr('GTD 设置','GTD settings')); dialog.resize(430,550); layout=QVBoxLayout(dialog)
            def action(zh,en,callback):
                button=QPushButton(self.tr(zh,en)); button.clicked.connect(callback); layout.addWidget(button)
            for platform in ('youtube','instagram','bilibili'):
                action('导入 '+platform+' Cookie','Import '+platform+' Cookie',lambda checked=False,p=platform:self.import_file(lambda source:import_cookies(source,root,p),'Cookie (*.txt);;All files (*)'))
            action('导入人工赛历 JSON','Import manual calendar JSON',lambda:self.import_file(lambda source:import_calendar(source,root),'JSON (*.json)'))
            action('导入任务历史（重启后生效）','Import history (restart required)',lambda:self.import_file(lambda source:stage_history_import(source,root),'SQLite (*.sqlite3 *.db);;All files (*)'))
            action('导入收藏','Import favorites',self.import_favorites); action('导出收藏','Export favorites',self.export_favorites)
            for zh,en,path in [('打开数据目录','Open data folder',root),('打开日志目录','Open logs folder',root/'logs')]:
                action(zh,en,lambda checked=False,p=path:QDesktopServices.openUrl(QUrl.fromLocalFile(str(p))))
            from gtd_paths import downloads_root
            action('打开下载目录','Open downloads folder',lambda:QDesktopServices.openUrl(QUrl.fromLocalFile(str(downloads_root()))))
            action('关闭','Close',dialog.accept); dialog.exec()
        def import_file(self, callback, filters):
            source,_=QFileDialog.getOpenFileName(self,self.tr('选择导入文件','Choose import file'),'',filters)
            if not source:return
            try: callback(Path(source))
            except Exception: QMessageBox.warning(self,'GTD',self.tr('导入失败：文件无效或无法写入。原数据已保留。','Import failed: invalid file or write error. Existing data was preserved.')); return
            QMessageBox.information(self,'GTD',self.tr('导入完成。历史导入需重启。','Import complete. History imports require restart.'))
        def import_favorites(self):
            def apply(source):
                value=validate_favorites(json.loads(read_bounded(source,1024*1024)))
                self.page.runJavaScript("localStorage.setItem('gtd_lmu_favorites_v1',"+json.dumps(json.dumps(value))+");")
                self.view.reload()
            self.import_file(apply,'JSON (*.json)')
        def export_favorites(self):
            target,_=QFileDialog.getSaveFileName(self,self.tr('导出收藏','Export favorites'),'gtd-favorites.json','JSON (*.json)')
            if not target:return
            def save(value):
                try: atomic_write(target,(json.dumps(validate_favorites(json.loads(value or '{"circuits":[],"cars":[]}')),ensure_ascii=False,indent=2)+'\n').encode())
                except Exception: QMessageBox.warning(self,'GTD',self.tr('收藏导出失败。','Favorites export failed.'))
            self.page.runJavaScript("localStorage.getItem('gtd_lmu_favorites_v1')",save)
        def closeEvent(self,event):
            active=[]
            for batch in app_module.task_manager.list_batches():
                for task in app_module.task_manager.snapshot(batch['id']).get('tasks',[]):
                    if task['status'] not in ('completed','failed','cancelled'):
                        if not task.get('can_cancel',False):
                            QMessageBox.information(self,'GTD',self.tr('任务正在不可中断的阶段，请完成后退出。','A task is in an uninterruptible stage. Please wait before quitting.')); event.ignore(); return
                        active.append((batch['id'],task['id']))
            if active:
                answer=QMessageBox.question(self,'GTD',self.tr('仍有任务运行。取消任务并退出？','Tasks are active. Cancel them and quit?'),QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,QMessageBox.StandardButton.No)
                if answer!=QMessageBox.StandardButton.Yes:event.ignore();return
                for batch,task in active:
                    try:app_module.task_manager.cancel(batch,task)
                    except (KeyError,ValueError):pass
            self.closing=True; self.timer.stop(); self.view.setPage(QWebEnginePage(self.view)); self.page.deleteLater(); event.accept()
    application = QApplication.instance() or QApplication([])
    window = Window(); window.show()
    # Polish once after the native window is visible, including default preferences.
    QTimer.singleShot(0, window.paint)
    return application.exec()
