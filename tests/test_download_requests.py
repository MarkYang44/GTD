"""Request parsing is independent of Flask and keeps public rejection semantics."""

import importlib.util
from pathlib import Path
import tempfile
import unittest

from collection_resolver import CollectionEntry, CollectionPreview, PreviewStore
from output_files import prepare_output_dir


class DownloadRequestTests(unittest.TestCase):
    def module(self):
        self.assertIsNotNone(importlib.util.find_spec("download_requests"),
                             "download requests need a Flask-independent boundary")
        import download_requests
        return download_requests

    def test_mixed_urls_preserve_rejected_indexes_and_normalize_share_text(self):
        parser = self.module()
        with tempfile.TemporaryDirectory() as temporary:
            parsed = parser.parse_download_request({
                "urls": ["", "分享 https://youtu.be/example。", "https://example.com/clip"],
                "download_dir": temporary,
            }, previews=PreviewStore())
            self.assertEqual([(seed.platform, seed.url) for seed in parsed.seeds],
                             [("youtube", "https://youtu.be/example")])
            self.assertEqual([item["index"] for item in parsed.rejected], [1, 3])
            self.assertEqual([item["error_code"] for item in parsed.rejected],
                             ["INVALID_URL", "UNSUPPORTED_PLATFORM"])
            self.assertEqual(str(parsed.output_dir), str(Path(temporary).resolve()))

    def test_preview_selection_keeps_user_order_and_source_metadata(self):
        parser = self.module()
        previews = PreviewStore()
        entries = tuple(CollectionEntry(str(n), f"Part {n}", "bilibili",
                        f"https://b23.tv/part{n}", n, None, True, None) for n in (1, 2))
        previews.put(CollectionPreview("preview", "Parts", "bilibili", entries, False))
        with tempfile.TemporaryDirectory() as temporary:
            parsed = parser.parse_download_request({"preview_id": "preview",
                "selected_entry_ids": ["2", "1"], "download_dir": temporary}, previews=previews)
            self.assertEqual([(seed.title, seed.position) for seed in parsed.seeds],
                             [("Part 2", 2), ("Part 1", 1)])

    def test_expired_preview_retains_retryable_structured_error(self):
        parser = self.module()
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(parser.DownloadRequestError) as caught:
                parser.parse_download_request({"preview_id": "missing", "selected_entry_ids": ["1"],
                    "download_dir": temporary}, previews=PreviewStore())
        self.assertEqual(caught.exception.error_code, "PREVIEW_EXPIRED")
        self.assertEqual(caught.exception.status, 404)
        self.assertTrue(caught.exception.retryable)

    def test_invalid_settings_fail_before_preparing_output_directory(self):
        parser = self.module()
        prepared = []
        def prepare(value):
            prepared.append(value)
            return prepare_output_dir(value)
        with self.assertRaises(parser.DownloadRequestError) as caught:
            parser.parse_download_request({"urls": ["https://youtu.be/example"],
                "audio_format": ["mp3"]}, previews=PreviewStore(), prepare_directory=prepare)
        self.assertEqual(caught.exception.status, 400)
        self.assertEqual(caught.exception.error_code, "INVALID_REQUEST")
        self.assertEqual(prepared, [])
