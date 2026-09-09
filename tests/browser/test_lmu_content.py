"""Source notes, review metadata, comparison, and content history in Chromium."""
from playwright.sync_api import expect
from test_reliability import BrowserReliabilityTests


class LmuContentBrowserTests(BrowserReliabilityTests):
    def test_notes_and_pairing_metadata_survive_comparison(self):
        self.page.goto(self.url + '/kozekilmu/tracks')
        note = self.page.locator('#bahrain > .circuit-content > [data-practice]')
        note.locator('summary').click()
        expect(note).to_contain_text('tire degradation')
        expect(note).to_contain_text('2026-09-09')
        self.page.locator('#bahrain details[data-recommendations] > summary').click()
        recs = self.page.locator('#bahrain .recommendation')
        review = recs.first.locator('[data-content-review]')
        review.locator('summary').click()
        expect(review).to_contain_text('Unverified')
        expect(review.locator('a')).to_have_count(2)
        recs.nth(0).locator('[data-compare]').click()
        recs.nth(1).locator('[data-compare]').click()
        self.page.locator('#lmu-open-compare').click()
        expect(self.page.locator('#lmu-compare-grid [data-content-review]')).to_have_count(2)
        expect(self.page.locator('#lmu-compare-grid [data-practice]')).to_have_count(2)
        self.assertEqual(self.errors, [])

    def test_history_and_notes_are_bilingual_and_fit_mobile(self):
        self.page.set_viewport_size({'width': 375, 'height': 800})
        self.page.goto(self.url + '/kozekilmu/updates')
        self.page.locator('.lmu-change-group').first.locator(':scope > summary').click()
        change = self.page.locator('.lmu-change').first
        change.locator('summary').click()
        expect(change).to_contain_text('Before:')
        expect(change).to_contain_text('After:')
        self.page.locator('#guide-language-toggle').focus()
        self.page.keyboard.press('Space')
        expect(change).to_contain_text('之前：')
        self.assertTrue(self.page.evaluate('document.documentElement.scrollWidth <= innerWidth'))
        self.page.goto(self.url + '/kozekilmu/cars')
        expect(self.page.locator('[data-practice]')).to_have_count(16)
        self.page.locator('[data-practice]').first.locator('summary').click()
        expect(self.page.locator('[data-practice]').first).to_contain_text('据资料整理')
        self.assertTrue(self.page.evaluate('document.documentElement.scrollWidth <= innerWidth'))
        self.assertEqual(self.errors, [])

    def test_sources_and_history_work_without_javascript(self):
        context = self.browser.new_context(java_script_enabled=False)
        try:
            page = context.new_page()
            page.goto(self.url + '/kozekilmu/cars')
            note = page.locator('[data-practice]').first
            note.locator('summary').click()
            expect(note.locator('a')).to_be_visible()
            page.goto(self.url + '/kozekilmu/updates')
            page.locator('.lmu-change-group').first.locator(':scope > summary').click()
            change = page.locator('.lmu-change').first
            change.locator('summary').click()
            expect(change.locator('.lmu-change-field').first).to_be_visible()
        finally:
            context.close()


for _name in dir(BrowserReliabilityTests):
    if _name.startswith('test_'):
        setattr(LmuContentBrowserTests, _name, None)
del BrowserReliabilityTests
