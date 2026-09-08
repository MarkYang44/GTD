"""Real browser checks for the race evidence carousel."""
from playwright.sync_api import expect
from test_reliability import BrowserReliabilityTests


class GalleryBrowserTests(BrowserReliabilityTests):
    def test_gallery_navigation_language_and_resize(self):
        self.page.goto(self.url + '/kozekilmu')
        track = self.page.locator('#race-gallery')
        track.scroll_into_view_if_needed()
        expect(self.page.locator('.gallery-count')).to_have_text('1 / 5')
        expect(self.page.get_by_role('button', name='Previous image', exact=True)).to_be_disabled()
        self.page.get_by_role('button', name='Next image', exact=True).click()
        self.page.wait_for_function("Math.abs(document.querySelector('#race-gallery').scrollLeft - document.querySelector('#race-gallery').clientWidth) < 2")
        expect(self.page.locator('.gallery-count')).to_have_text('2 / 5')
        self.page.get_by_role('button', name='View image 5', exact=True).click()
        self.page.wait_for_function("Math.abs(document.querySelector('#race-gallery').scrollLeft - 4 * document.querySelector('#race-gallery').clientWidth) < 2")
        expect(self.page.get_by_role('button', name='Next image', exact=True)).to_be_disabled()
        self.page.set_viewport_size({'width': 375, 'height': 667})
        self.page.wait_for_function("Math.abs(document.querySelector('#race-gallery').scrollLeft - 4 * document.querySelector('#race-gallery').clientWidth) < 2")
        track.focus()
        self.page.keyboard.press('Home')
        self.page.wait_for_function("document.querySelector('#race-gallery').scrollLeft < 2")
        self.page.locator('#guide-language-toggle').focus()
        self.page.keyboard.press('Space')
        expect(self.page.get_by_role('button', name='下一张', exact=True)).to_be_visible()
        self.assertTrue(self.page.evaluate('document.documentElement.scrollWidth <= innerWidth'))
        self.assertEqual(self.errors, [])

    def test_gallery_native_fallback_and_reduced_motion(self):
        context = self.browser.new_context(java_script_enabled=False, viewport={'width': 375, 'height': 667})
        try:
            page = context.new_page()
            page.goto(self.url + '/kozekilmu')
            track = page.locator('#race-gallery')
            track.scroll_into_view_if_needed()
            expect(track.locator('img')).to_have_count(5)
            track.focus()
            page.keyboard.press('End')
            self.assertTrue(track.evaluate('(el) => el.scrollWidth > el.clientWidth'))
            self.assertEqual(track.locator('img').first.evaluate('(el) => getComputedStyle(el).objectFit'), 'contain')
        finally:
            context.close()
        self.page.emulate_media(reduced_motion='reduce')
        self.page.goto(self.url + '/kozekilmu')
        self.page.get_by_role('button', name='View image 3', exact=True).click()
        expect(self.page.locator('.gallery-count')).to_have_text('3 / 5')
        self.page.wait_for_function("Math.abs(document.querySelector('#race-gallery').scrollLeft - 2 * document.querySelector('#race-gallery').clientWidth) < 2")


for _name in dir(BrowserReliabilityTests):
    if _name.startswith('test_'):
        setattr(GalleryBrowserTests, _name, None)
del BrowserReliabilityTests
