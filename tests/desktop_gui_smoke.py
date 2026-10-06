"""Opt-in native macOS/Windows GUI smoke: python tests/desktop_gui_smoke.py.

Requires desktop dependencies and GUI access. Uses isolated data and port 18234.
Report paths may be overridden via GTD_GUI_SMOKE_REPORT/SCREENSHOT.
"""
import sys, tempfile, json, os
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from gtd_paths import initialize_desktop
root=Path(tempfile.mkdtemp(prefix='gtd-window-smoke-'));initialize_desktop(root)
import app
app.folder_picker_available = lambda: False
from desktop_server import DesktopServer
from desktop_window import run_window, NAVIGATION
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer,QUrl
qt=QApplication([])
server=DesktopServer(app.app,'test-window-token',port=18234)
base=server.start()
results=[]; route_index=0

def start():
    window=qt.activeWindow()
    if window is None:QTimer.singleShot(100,start);return
    capability=app.app.test_client().get('/api/capabilities',base_url=base,headers={'X-GTD-Desktop-Token':'test-window-token'}).get_json()
    assert capability['folder_picker_available'] is True, 'Qt picker capability did not override unavailable OS backend'
    def loaded(ok):
        global route_index
        route=NAVIGATION[route_index][0]
        def collect(value):
            global route_index
            results.append({'route':route,'ok':ok,'document':json.loads(value) if value else None})
            if route_index==0:
                window.grab().save(os.environ.get('GTD_GUI_SMOKE_SCREENSHOT',str(Path(tempfile.gettempdir())/'gtd-native-window.png')))
            route_index+=1
            if route_index<len(NAVIGATION):QTimer.singleShot(100,lambda:window.view.setUrl(QUrl(base+NAVIGATION[route_index][0])))
            else:
                Path(os.environ.get('GTD_GUI_SMOKE_REPORT',str(Path(tempfile.gettempdir())/'gtd-window-smoke.json'))).write_text(json.dumps(results,ensure_ascii=False,indent=2))
                QTimer.singleShot(100,window.close)
        window.page.runJavaScript("JSON.stringify({title:document.title,text:document.body.innerText.slice(0,200),theme:document.documentElement.dataset.theme,language:document.documentElement.lang})",collect)
    window.view.loadFinished.connect(loaded)
    if window.view.url().isEmpty():return
QTimer.singleShot(10,start)
QTimer.singleShot(45000,qt.quit)
try:run_window(base,'test-window-token',root,app)
finally:server.close();app.task_manager.shutdown(wait=True)
print(json.dumps(results,ensure_ascii=False))

assert len(results)==len(NAVIGATION), 'GUI smoke did not finish all routes'
assert all(item['ok'] and item['document'] and item['document']['text'] for item in results), 'A desktop route failed to render'
