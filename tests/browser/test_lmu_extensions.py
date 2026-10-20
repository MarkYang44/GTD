"""Catalog reuse, language and layout behavior in a real browser."""
from playwright.sync_api import expect
from test_reliability import BrowserReliabilityTests


class LmuExtensionsBrowserTests(BrowserReliabilityTests):
    def test_catalog_shares_favorites_filters_and_comparison(self):
        self.page.goto(self.url + '/kozekilmu/tracks')
        self.page.locator('[data-favorite-circuit="bahrain"]').click()
        self.page.locator('#bahrain details[data-recommendations] > summary').click()
        self.page.locator('#bahrain [data-favorite-car]').first.click()
        stored = self.page.evaluate('JSON.parse(localStorage.getItem("gtd_lmu_favorites_v1"))')
        car = stored['cars'][0]
        self.page.goto(self.url + '/kozekilmu/cars')
        expect(self.page.locator(f'[data-favorite-car="{car}"]')).to_have_attribute('aria-pressed', 'true')
        self.page.locator('#lmu-favorites').select_option('cars')
        expect(self.page.locator('.catalog-card:visible')).to_have_count(1)
        self.page.locator('#lmu-reset').click()
        self.page.locator('#lmu-class').select_option('Hypercar')
        expect(self.page.locator('.catalog-card:visible')).not_to_have_count(0)
        self.assertTrue(all(n.get_attribute('data-class') == 'Hypercar' for n in self.page.locator('.recommendation:visible').all()))
        self.page.locator('#lmu-reset').click()
        self.page.locator('#lmu-search').fill('Ferrari')
        expect(self.page.locator('.catalog-card:visible')).to_have_count(2)
        self.page.locator('.catalog-card:visible [data-compare]').nth(0).click()
        self.page.locator('.catalog-card:visible [data-compare]').nth(1).click()
        self.page.locator('#lmu-open-compare').click()
        expect(self.page.locator('.lmu-compare-card')).to_have_count(2)
        expect(self.page.locator('.lmu-compare-card').first).to_contain_text('Recommended at')
        self.page.keyboard.press('Escape')
        self.page.locator('.catalog-card:visible [data-favorite-car]').first.click()
        stored = self.page.evaluate('JSON.parse(localStorage.getItem("gtd_lmu_favorites_v1"))')
        self.assertIn('bahrain', stored['circuits'])
        self.page.goto(self.url + '/kozekilmu/tracks')
        expect(self.page.locator('[data-favorite-circuit="bahrain"]')).to_have_attribute('aria-pressed', 'true')
        self.assertEqual(self.errors, [])

    def test_catalog_language_and_mobile_layout(self):
        self.page.goto(self.url + '/kozekilmu/cars')
        self.page.set_viewport_size({'width': 375, 'height': 812})
        expect(self.page.locator('#lmu-tools')).to_be_visible()
        self.page.locator('label[for="guide-language-toggle"]').click()
        expect(self.page.locator('html')).to_have_attribute('data-guide-language', 'zh')
        self.assertTrue(self.page.evaluate('document.documentElement.scrollWidth <= innerWidth'))
        self.assertEqual(self.errors, [])


for _name in dir(BrowserReliabilityTests):
    if _name.startswith('test_'):
        setattr(LmuExtensionsBrowserTests, _name, None)
del BrowserReliabilityTests
