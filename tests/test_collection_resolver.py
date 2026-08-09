import unittest
from unittest.mock import MagicMock, patch

import collection_resolver as resolver


class CollectionResolverTests(unittest.TestCase):
    def _factory(self, info):
        ydl = MagicMock()
        ydl.__enter__.return_value = ydl
        ydl.extract_info.return_value = info
        return lambda options: ydl

    def test_youtube_playlist_preserves_order_and_disabled_entries(self):
        info = {
            "_type": "playlist",
            "title": "Playlist",
            "entries": [
                {
                    "id": "one",
                    "title": "One",
                    "url": "https://youtu.be/one",
                    "thumbnail": "https://img/one.jpg",
                },
                {
                    "id": "gone",
                    "title": "Deleted video",
                    "url": None,
                    "availability": "private",
                },
                {
                    "id": "two",
                    "title": "Two",
                    "url": "https://youtu.be/two",
                },
            ],
        }
        preview = resolver.resolve_collection(
            "https://www.youtube.com/playlist?list=PL123",
            ydl_factory=self._factory(info),
        )

        self.assertEqual([entry.position for entry in preview.entries], [1, 2, 3])
        self.assertTrue(preview.entries[0].selectable)
        self.assertFalse(preview.entries[1].selectable)
        self.assertTrue(preview.requires_selection)

    def test_bilibili_multipart_builds_distinct_p_urls(self):
        info = {
            "_type": "multi_video",
            "id": "BV123",
            "title": "Parts",
            "entries": [
                {
                    "id": "BV123_p1",
                    "title": "P1",
                    "url": "https://www.bilibili.com/video/BV123?p=1",
                },
                {
                    "id": "BV123_p2",
                    "title": "P2",
                    "url": "https://www.bilibili.com/video/BV123?p=2",
                },
            ],
        }
        preview = resolver.resolve_collection(
            "https://www.bilibili.com/video/BV123",
            ydl_factory=self._factory(info),
        )

        self.assertNotEqual(preview.entries[0].url, preview.entries[1].url)
        self.assertIn("p=2", preview.entries[1].url)

    def test_instagram_carousel_entries_remain_separate(self):
        info = {
            "_type": "playlist",
            "id": "carousel",
            "title": "Post",
            "entries": [
                {
                    "id": "photo",
                    "title": "Photo",
                    "url": "https://www.instagram.com/p/post/?__a=1",
                },
                {
                    "id": "video",
                    "title": "Video",
                    "url": "https://www.instagram.com/p/post/?__a=2",
                },
            ],
        }
        preview = resolver.resolve_collection(
            "https://www.instagram.com/p/post/",
            ydl_factory=self._factory(info),
        )

        self.assertEqual(len(preview.entries), 2)
        self.assertEqual([entry.position for entry in preview.entries], [1, 2])

    def test_selection_rejects_more_than_100_and_unknown_ids(self):
        entries = tuple(
            resolver.CollectionEntry(
                str(index),
                str(index),
                "youtube",
                f"https://youtu.be/{index}",
                index,
                None,
                True,
                None,
            )
            for index in range(1, 102)
        )
        preview = resolver.CollectionPreview(
            "p",
            "title",
            "youtube",
            entries,
            False,
        )

        with self.assertRaisesRegex(ValueError, "最多选择 100"):
            resolver.select_preview_entries(
                preview,
                [entry.id for entry in entries],
            )
        with self.assertRaisesRegex(ValueError, "条目不存在"):
            resolver.select_preview_entries(preview, ["missing"])

    def test_mixed_inputs_merge_single_and_collection_entries_in_input_order(self):
        single = resolver.CollectionPreview(
            "single",
            "Single",
            "youtube",
            (
                resolver.CollectionEntry(
                    "1:a",
                    "A",
                    "youtube",
                    "https://youtu.be/a",
                    1,
                    None,
                    True,
                    None,
                ),
            ),
            True,
        )
        collection = resolver.CollectionPreview(
            "collection",
            "Parts",
            "bilibili",
            (
                resolver.CollectionEntry(
                    "1:p1",
                    "P1",
                    "bilibili",
                    "https://bilibili.com/video/BV1?p=1",
                    1,
                    None,
                    True,
                    None,
                ),
                resolver.CollectionEntry(
                    "2:p2",
                    "P2",
                    "bilibili",
                    "https://bilibili.com/video/BV1?p=2",
                    2,
                    None,
                    True,
                    None,
                ),
            ),
            False,
        )
        with patch(
            "collection_resolver.resolve_collection",
            side_effect=[single, collection],
        ):
            merged = resolver.resolve_inputs(
                ["https://youtu.be/a", "https://b23.tv/list"]
            )

        self.assertEqual(
            [entry.title for entry in merged.entries],
            ["A", "P1", "P2"],
        )
        self.assertEqual(merged.platform, "mixed")
        self.assertFalse(merged.is_single)
        self.assertTrue(merged.requires_selection)

    def test_collection_detection_is_limited_to_supported_paths(self):
        self.assertEqual(
            resolver.detect_collection_platform(
                "https://www.youtube.com/playlist?list=PL123"
            ),
            resolver.YOUTUBE,
        )
        self.assertEqual(
            resolver.detect_collection_platform(
                "https://space.bilibili.com/123/lists/456"
            ),
            resolver.BILIBILI,
        )
        self.assertIsNone(
            resolver.detect_collection_platform(
                "https://www.youtube.com/@creator/videos"
            )
        )
        self.assertIsNone(
            resolver.detect_collection_platform(
                "https://space.bilibili.com/123/video"
            )
        )

    def test_extractor_error_is_classified_without_public_raw_text(self):
        ydl = MagicMock()
        ydl.__enter__.return_value = ydl
        ydl.extract_info.side_effect = RuntimeError(
            "extractor crashed token=secret"
        )

        with self.assertRaises(resolver.CollectionResolveError) as raised:
            resolver.resolve_collection(
                "https://www.youtube.com/playlist?list=PL123",
                ydl_factory=lambda options: ydl,
            )

        self.assertEqual(
            raised.exception.info.error_code,
            "COLLECTION_EXTRACT_FAILED",
        )
        self.assertNotIn("secret", raised.exception.info.message)


class PreviewStoreTests(unittest.TestCase):
    def test_expired_preview_is_removed(self):
        preview = resolver.CollectionPreview(
            "preview",
            "Title",
            "youtube",
            (),
            False,
        )
        store = resolver.PreviewStore(ttl_seconds=10)
        with patch("collection_resolver.time.monotonic", side_effect=[1, 12]):
            store.put(preview)
            self.assertIsNone(store.get(preview.id))


if __name__ == "__main__":
    unittest.main()
