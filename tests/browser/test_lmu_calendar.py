"""Real calendar rendering with isolated synthetic data (never live publication)."""
import os
from pathlib import Path
import tempfile
from unittest.mock import patch
from playwright.sync_api import expect
from test_reliability import BrowserReliabilityTests
from tests.test_lmu_calendar import calendar_fixture
from lmu_calendar import publish_calendar


class CalendarBrowserTests(BrowserReliabilityTests):
    def setUp(self):
        self.context = self.browser.new_context(viewport={'width':1280,'height':800})
        self.addCleanup(self.context.close)
        self.context.add_init_script("if (!localStorage.getItem('gtd_language_v1')) localStorage.setItem('gtd_language_v1','en')")
        self.page = self.context.new_page()
        self.errors = []
        self.page.on('pageerror', lambda error: self.errors.append(str(error)))
        self.context.route('https://**/*', lambda route: route.abort())
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.settings = patch.dict(os.environ, {'GTD_LMU_CALENDAR_DIR': directory.name})
        self.settings.start(); self.addCleanup(self.settings.stop)
        publish_calendar(calendar_fixture(), self.root)

    def test_sessions_estimates_language_theme_and_responsive_layout(self):
        self.page.goto(self.url + '/kozekilmu/calendar')
        self.page.locator('.calendar-details > summary').nth(0).click()
        expect(self.page.locator('.calendar-sessions')).to_contain_text('01:30 BST')
        expect(self.page.locator('.calendar-sessions')).to_contain_text('01:30 GMT')
        self.page.locator('.calendar-details > summary').nth(1).click()
        self.page.locator('.calendar-car summary').click()
        expect(self.page.locator('.calendar-car')).to_contain_text('Version evidence')
        self.page.locator('.calendar-details > summary').nth(2).click()
        expect(self.page.locator('[data-calendar-result]')).to_contain_text('Estimated laps: 16')
        expect(self.page.locator('[data-calendar-result]')).to_contain_text('23.1 L / 22.8 L')
        for width in (1440, 768, 375, 320):
            self.page.set_viewport_size({'width': width, 'height': 900})
            self.assertTrue(self.page.evaluate('document.documentElement.scrollWidth <= innerWidth'))
        self.page.locator('label[for="guide-language-toggle"]').click()
        expect(self.page.locator('[data-calendar-result]')).to_contain_text('估算圈数：16')
        self.page.locator('label[for="theme-toggle"]').click()
        expect(self.page.locator('html')).to_have_attribute('data-theme','light')
        self.page.reload()
        expect(self.page.locator('html')).to_have_attribute('data-guide-language','zh')
        self.page.set_viewport_size({'width':1440,'height':1000})
        self.page.locator('.calendar-details > summary').nth(2).click()
        self.page.evaluate('scrollTo(0,0)')
        self.page.screenshot(path='/tmp/gtd-calendar-desktop.png', full_page=True, animations='disabled')
        self.page.set_viewport_size({'width':375,'height':812})
        self.page.evaluate('scrollTo(0,0)')
        self.page.screenshot(path='/tmp/gtd-calendar-mobile.png', full_page=True, animations='disabled')
        self.page.locator('label[for="guide-language-toggle"]').click()
        visible_text = self.page.locator('body').inner_text()
        self.assertFalse(any('\u4e00' <= char <= '\u9fff' for char in visible_text))

    def test_fallback_failure_empty_offline_and_no_javascript(self):
        invalid = calendar_fixture(); invalid['events'][0]['track'] = ''
        try: publish_calendar(invalid,self.root)
        except ValueError: pass
        self.page.goto(self.url + '/kozekilmu/calendar')
        expect(self.page.locator('.calendar-notices')).to_contain_text('Update failed')
        self.page.evaluate("Object.defineProperty(navigator, 'onLine', {get:()=>false}); dispatchEvent(new Event('offline'))")
        expect(self.page.locator('#calendar-offline')).to_be_visible()
        plain = self.browser.new_context(java_script_enabled=False)
        self.addCleanup(plain.close)
        page = plain.new_page(); page.route('https://**/*', lambda route: route.abort())
        page.goto(self.url + '/kozekilmu/calendar')
        page.locator('.calendar-details > summary').nth(0).click()
        expect(page.locator('.calendar-sessions')).to_contain_text('01:30 BST')
        page.locator('.calendar-details > summary').nth(2).click()
        expect(page.locator('.calendar-strategy noscript [data-guide-copy="zh"]')).to_be_visible()
        self.assertTrue(page.evaluate('document.documentElement.scrollWidth <= innerWidth'))
        (self.root/'current.json').write_text('broken')
        self.page.reload()
        expect(self.page.locator('.calendar-notices')).to_contain_text('valid local backup')
        (self.root/'current.json').unlink()
        (self.root/'previous.json').unlink()
        self.page.reload()
        expect(self.page.locator('.calendar-notices')).to_contain_text('No calendar published')


for _name in dir(BrowserReliabilityTests):
    if _name.startswith('test_'):
        setattr(CalendarBrowserTests, _name, None)
del BrowserReliabilityTests
