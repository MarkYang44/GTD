import unittest

import downloader


class BilibiliUrlDetectionTests(unittest.TestCase):
    def test_accepts_single_video_and_short_link_urls(self):
        accepted = [
            "https://www.bilibili.com/video/BV1GJ411x7h7",
            "https://www.bilibili.com/video/av170001?p=2",
            "https://m.bilibili.com/video/BV1GJ411x7h7",
            "https://bilibili.com/video/av170001",
            "https://b23.tv/BV1GJ411x7h7",
        ]

        for url in accepted:
            with self.subTest(url=url):
                self.assertEqual(
                    downloader.detect_platform(url),
                    downloader.BILIBILI,
                )
                self.assertTrue(downloader.is_valid_bilibili_url(url))
                self.assertEqual(
                    downloader.make_task(url),
                    (downloader.BILIBILI, url),
                )

    def test_rejects_non_video_bilibili_pages(self):
        rejected = [
            "https://space.bilibili.com/2",
            "https://www.bilibili.com/bangumi/play/ep1",
            "https://www.bilibili.com/list/watchlater",
            "https://www.bilibili.com/medialist/play/1",
            "https://www.bilibili.com/video/",
            "https://www.bilibili.com/video/not-a-video-id",
            "https://b23.tv/",
        ]

        for url in rejected:
            with self.subTest(url=url):
                self.assertIsNone(downloader.detect_platform(url))
                self.assertFalse(downloader.is_valid_bilibili_url(url))


if __name__ == "__main__":
    unittest.main()
