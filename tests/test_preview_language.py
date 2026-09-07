import unittest
from unittest.mock import MagicMock

import collection_resolver as resolver


class PreviewLanguageTests(unittest.TestCase):
    def factory(self, *metadata):
        ydl = MagicMock()
        ydl.__enter__.return_value = ydl
        ydl.extract_info.side_effect = metadata
        return lambda options: ydl

    def test_multiple_inputs_mark_only_generated_titles(self):
        preview = resolver.resolve_inputs(
            ["https://youtu.be/one", "https://youtu.be/two"],
            ydl_factory=self.factory(
                {"id": "one", "title": "第 1 项"},
                {"id": "two"},
            ),
        ).to_dict()
        self.assertEqual(preview["title"], "下载预览（2 项）")
        self.assertIs(preview.get("title_is_generated"), True)
        self.assertEqual(preview["entries"][0]["title"], "第 1 项")
        self.assertIs(preview["entries"][0].get("title_is_generated"), False)
        self.assertIs(preview["entries"][1].get("title_is_generated"), True)
        self.assertEqual(preview["entries"][1]["position"], 2)

    def test_single_input_preserves_source_title_even_when_it_matches_fallback(self):
        preview = resolver.resolve_inputs(
            ["https://youtu.be/one"],
            ydl_factory=self.factory({"id": "one", "title": "下载预览（2 项）"}),
        ).to_dict()
        self.assertEqual(preview["title"], "下载预览（2 项）")
        self.assertIs(preview.get("title_is_generated"), False)
        self.assertIs(preview["entries"][0].get("title_is_generated"), False)

    def test_single_input_marks_missing_title(self):
        preview = resolver.resolve_inputs(
            ["https://youtu.be/one"], ydl_factory=self.factory({"id": "one"}),
        ).to_dict()
        self.assertIs(preview.get("title_is_generated"), True)
        self.assertIs(preview["entries"][0].get("title_is_generated"), True)

    def test_collection_inherits_title_origin_from_first_entry(self):
        for title, expected in [("真实标题", False), (None, True)]:
            with self.subTest(title=title):
                preview = resolver.resolve_collection(
                    "https://www.youtube.com/playlist?list=PL123",
                    ydl_factory=self.factory({
                        "_type": "playlist", "entries": [{"id": "one", "title": title}],
                    }),
                ).to_dict()
                self.assertIs(preview.get("title_is_generated"), expected)

    def test_empty_collection_preserves_source_title_or_marks_fallback(self):
        for title, expected in [("真实合集", False), (None, True)]:
            with self.subTest(title=title):
                preview = resolver.resolve_collection(
                    "https://www.youtube.com/playlist?list=PL123",
                    ydl_factory=self.factory({"_type": "playlist", "title": title, "entries": []}),
                ).to_dict()
                self.assertEqual(preview["title"], title or "未命名合集")
                self.assertIs(preview.get("title_is_generated"), expected)
