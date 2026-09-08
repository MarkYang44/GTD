"""Progressively enhanced LMU tools, real DOM and shared language/theme runtime."""
from playwright.sync_api import expect
from test_reliability import BrowserReliabilityTests


class LmuToolsBrowserTests(BrowserReliabilityTests):
    # Reuse isolated server/browser setup without running the base class tests twice.
    def test_lmu_search_filters_and_reset(self):
        self.page.goto(self.url + '/kozekilmu/tracks')
        expect(self.page.locator('#lmu-tools')).to_be_visible()
        self.page.locator('#lmu-search').fill('富士')
        expect(self.page.locator('.circuit-card:visible')).to_have_count(1)
        expect(self.page.locator('#fuji')).to_be_visible()
        self.page.locator('#lmu-class').select_option('LMGT3')
        expect(self.page.locator('#fuji .recommendation:not([hidden])')).to_have_count(3)
        self.page.locator('#lmu-search').fill('no-such-circuit')
        expect(self.page.locator('#lmu-empty')).to_be_visible()
        self.page.locator('#lmu-reset').click()
        expect(self.page.locator('.circuit-card:visible')).to_have_count(16)
        self.page.locator('#lmu-search').fill('portimao')
        expect(self.page.locator('#portimao')).to_be_visible()
        expect(self.page.locator('.circuit-card:visible')).to_have_count(1)

    def test_lmu_favorites_persist_and_comparison_has_context(self):
        self.page.goto(self.url + '/kozekilmu/tracks')
        self.page.locator('[data-favorite-circuit="bahrain"]').click()
        self.page.reload()
        expect(self.page.locator('[data-favorite-circuit="bahrain"]')).to_have_attribute('aria-pressed','true')
        self.page.locator('#lmu-favorites').select_option('circuits')
        expect(self.page.locator('.circuit-card:visible')).to_have_count(1)
        self.page.locator('#bahrain summary').click()
        buttons = self.page.locator('#bahrain [data-compare]')
        buttons.nth(0).click(); buttons.nth(1).click(); buttons.nth(2).click(); buttons.nth(3).click()
        expect(self.page.locator('#lmu-selection > *')).to_have_count(3)
        self.page.locator('#lmu-open-compare').click()
        expect(self.page.locator('#lmu-compare-dialog')).to_be_visible()
        expect(self.page.locator('.lmu-compare-card')).to_have_count(3)
        expect(self.page.locator('.lmu-compare-card').first).to_contain_text('Bahrain')
        self.page.keyboard.press('Escape')
        expect(self.page.locator('#lmu-compare-dialog')).not_to_be_visible()
        self.page.locator('#lmu-reset').click()
        expect(self.page.locator('#lmu-selection > *')).to_have_count(3)
        self.page.locator('#lmu-clear-compare').click()
        expect(self.page.locator('#lmu-compare-bar')).not_to_be_visible()

    def test_lmu_car_favorites_cross_tab_and_storage_failure(self):
        self.page.goto(self.url + '/kozekilmu/tracks')
        self.page.locator('#bahrain summary').click()
        favorite = self.page.locator('#bahrain [data-favorite-car]').first
        slug = favorite.get_attribute('data-favorite-car')
        favorite.click()
        for button in self.page.locator(f'[data-favorite-car="{slug}"]').all():
            expect(button).to_have_attribute('aria-pressed', 'true')
        self.page.locator('#lmu-favorites').select_option('cars')
        expected = self.page.locator(f'.recommendation[data-car="{slug}"]').count()
        expect(self.page.locator('.recommendation:not([hidden])')).to_have_count(expected)
        other = self.context.new_page()
        other.goto(self.url + '/kozekilmu/tracks')
        other.locator('#bahrain summary').click()
        self.page.locator(f'#bahrain [data-favorite-car="{slug}"]').focus()
        other.locator(f'#bahrain [data-favorite-car="{slug}"]').click()
        expect(self.page.locator('#lmu-empty')).to_be_visible()
        expect(self.page.locator('#lmu-favorites')).to_be_focused()
        other.close()
        blocked = self.browser.new_context()
        self.addCleanup(blocked.close)
        blocked.add_init_script("Object.defineProperty(window, 'localStorage', {get(){throw new Error('blocked')}})")
        page = blocked.new_page()
        page.route('https://**/*', lambda route: route.abort())
        page.goto(self.url + '/kozekilmu/tracks')
        expect(page.locator('#lmu-storage-note')).to_be_visible()
        page.locator('[data-favorite-circuit="fuji"]').click()
        page.locator('#lmu-favorites').select_option('circuits')
        expect(page.locator('.circuit-card:visible')).to_have_count(1)

    def test_lmu_mobile_compare_language_focus_and_no_javascript(self):
        self.page.set_viewport_size({'width':375,'height':800})
        self.context.add_init_script("localStorage.setItem('gtd_theme_v1','light')")
        self.page.goto(self.url + '/kozekilmu/tracks')
        self.assertLessEqual(self.page.evaluate('document.documentElement.scrollWidth'), 375)
        self.page.locator('#lmu-car').select_option('ferrari-296-lmgt3')
        self.assertGreater(self.page.locator('.circuit-card:visible').count(), 1)
        first = self.page.locator('.circuit-card:visible').first
        second = self.page.locator('.circuit-card:visible').nth(1)
        first.locator('summary').click(); first.locator('[data-compare]:visible').first.click()
        second.locator('summary').click(); second.locator('[data-compare]:visible').first.click()
        self.page.locator('label[for="guide-language-toggle"]').click()
        expect(self.page.locator('#lmu-class option').first).to_have_text('全部组别')
        self.page.locator('#lmu-open-compare').click()
        expect(self.page.locator('.lmu-compare-card')).to_have_count(2)
        contexts = self.page.locator('.lmu-compare-context').all_text_contents()
        self.assertNotEqual(contexts[0], contexts[1])
        self.assertLessEqual(self.page.evaluate('document.documentElement.scrollWidth'),375)
        self.page.locator('#lmu-compare-dialog [data-remove-compare]').first.click()
        expect(self.page.locator('#lmu-compare-dialog')).not_to_be_visible()
        expect(self.page.locator('#lmu-selection button').first).to_be_focused()
        plain = self.browser.new_context(java_script_enabled=False)
        self.addCleanup(plain.close)
        page = plain.new_page(); page.route('https://**/*', lambda route: route.abort())
        page.goto(self.url + '/kozekilmu/tracks')
        expect(page.locator('#lmu-tools')).not_to_be_visible()
        expect(page.locator('.circuit-card:visible')).to_have_count(16)
        page.locator('#bahrain summary').click()
        expect(page.locator('#bahrain .recommendation').first).to_be_visible()

# Only run new tests; lifecycle and API helpers above are intentionally shared.
for _name in dir(BrowserReliabilityTests):
    if _name.startswith('test_'):
        setattr(LmuToolsBrowserTests, _name, None)

del BrowserReliabilityTests
