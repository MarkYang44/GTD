"""Catalog reuse and race estimator behavior in a real browser."""
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

    def test_strategy_defaults_validation_and_mobile_language(self):
        self.page.goto(self.url + '/kozekilmu/strategy')
        expect(self.page.locator('#strategy-total')).to_have_text('52.8')
        expect(self.page.locator('#strategy-laps')).to_have_text('16')
        expect(self.page.locator('#strategy-assumptions')).to_contain_text('Defaults used:')
        self.page.locator('#strategy-minutes').fill('45')
        self.page.locator('#strategy-lap').fill('1:30')
        self.page.locator('#strategy-fuel').fill('2.6')
        expect(self.page.locator('#strategy-total')).to_have_text('88.7')
        self.page.locator('#strategy-lap').fill('1:99')
        expect(self.page.locator('#strategy-error')).to_be_visible()
        expect(self.page.locator('#strategy-result')).to_be_hidden()
        self.page.get_by_role('button', name='Use default estimates', exact=True).click()
        expect(self.page.locator('#strategy-total')).to_have_text('52.8')
        self.page.set_viewport_size({'width': 375, 'height': 667})
        self.page.locator('#guide-language-toggle').focus()
        self.page.keyboard.press('Space')
        expect(self.page.locator('#strategy-assumptions')).to_contain_text('使用默认值')
        self.assertTrue(self.page.evaluate('document.documentElement.scrollWidth <= innerWidth'))
        self.page.goto(self.url + '/kozekilmu/cars')
        expect(self.page.locator('#lmu-tools')).to_be_visible()
        self.assertTrue(self.page.evaluate('document.documentElement.scrollWidth <= innerWidth'))
        self.assertEqual(self.errors, [])


for _name in dir(BrowserReliabilityTests):
    if _name.startswith('test_'):
        setattr(LmuExtensionsBrowserTests, _name, None)
del BrowserReliabilityTests
