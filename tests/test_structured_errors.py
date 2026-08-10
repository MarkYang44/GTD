import contextlib
import io
import json
import logging
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from download_errors import (
    DownloadCancelled,
    classify_download_error,
    public_error,
)
from download_logging import (
    get_download_logger,
    log_download_event,
    redact_value,
    sanitize_url,
)


class StructuredErrorTests(unittest.TestCase):
    def test_network_timeout_is_retryable(self):
        info = classify_download_error(
            RuntimeError("socket timeout while connecting"),
            platform="youtube",
        )

        self.assertEqual(info.error_code, "NETWORK_TIMEOUT")
        self.assertTrue(info.retryable)
        self.assertIn("网络", info.message)

    def test_membership_failure_is_not_retryable(self):
        info = classify_download_error(
            RuntimeError("members only premium content"),
            platform="bilibili",
        )

        self.assertEqual(info.error_code, "MEMBERSHIP_REQUIRED")
        self.assertFalse(info.retryable)

    def test_public_error_excludes_technical_detail(self):
        payload = public_error(
            classify_download_error(RuntimeError("secret detail"))
        )

        self.assertEqual(
            set(payload),
            {"error_code", "message", "suggestion", "retryable"},
        )

    def test_cancelled_has_dedicated_code(self):
        self.assertEqual(DownloadCancelled().info.error_code, "CANCELLED")

    def test_collection_and_metadata_stages_have_dedicated_codes(self):
        collection = classify_download_error(
            RuntimeError("extractor changed"),
            stage="collection",
        )
        metadata = classify_download_error(
            RuntimeError("empty response"),
            stage="metadata",
        )

        self.assertEqual(collection.error_code, "COLLECTION_EXTRACT_FAILED")
        self.assertEqual(metadata.error_code, "METADATA_FAILED")


class DownloadLoggingTests(unittest.TestCase):
    def tearDown(self):
        logging.shutdown()

    def test_sanitize_url_drops_query_fragment_and_userinfo(self):
        value = sanitize_url(
            "https://user:password@www.bilibili.com/video/BV123"
            "?token=secret#fragment"
        )

        self.assertEqual(value, "https://www.bilibili.com/video/BV123")

    def test_jsonl_log_redacts_nested_secrets(self):
        with tempfile.TemporaryDirectory() as directory:
            logger = get_download_logger(Path(directory))
            log_download_event(
                logger,
                "failed",
                url="https://youtu.be/abc?token=secret",
                headers={"Authorization": "Bearer secret"},
                cookie="session=secret",
                proxy={"password": "secret"},
                error_code="NETWORK_TIMEOUT",
            )
            for handler in logger.handlers:
                handler.flush()
            line = (Path(directory) / "downloader.jsonl").read_text(
                encoding="utf-8"
            ).strip()
            payload = json.loads(line)
            rendered = json.dumps(payload, ensure_ascii=False)

            self.assertNotIn("secret", rendered)
            self.assertEqual(payload["event"], "failed")
            self.assertEqual(payload["url"], "https://youtu.be/abc")
            self.assertIn("timestamp", payload)
            for handler in logger.handlers:
                handler.close()

    def test_free_text_redacts_complete_headers_and_proxy_credentials(self):
        diagnostic = (
            "Authorization: Bearer top secret token\n"
            "Authorization=Basic another secret\n"
            "Cookie: session=abc def; preference=dark\n"
            "proxy=https://user:proxy-pass@proxy.example:7890/path\n"
            "token=plain-secret"
        )

        rendered = str(redact_value(diagnostic))

        for secret in (
            "top secret token",
            "another secret",
            "session=abc def",
            "proxy-pass",
            "plain-secret",
        ):
            self.assertNotIn(secret, rendered)
        self.assertIn("Authorization=[redacted]", rendered)

    def test_nested_secret_key_variants_and_spaced_tokens_are_redacted(self):
        payload = {
            "Proxy-Authorization": "Basic proxy-secret",
            "proxy_username": "proxy-user",
            "access_token": "access-secret",
            "refresh_token": "refresh-secret",
            "session_id": "session-secret",
            "api_key": "api-secret",
            "API-Key": "header-api-secret",
            "diagnostic": (
                "token=top secret value\n"
                "api_key=raw api secret\n"
                "proxy_username=raw proxy user\n"
                "session_id=raw session secret\n"
                "next=visible"
            ),
        }

        rendered = json.dumps(redact_value(payload), ensure_ascii=False)

        for secret in (
            "proxy-secret",
            "proxy-user",
            "access-secret",
            "refresh-secret",
            "session-secret",
            "api-secret",
            "header-api-secret",
            "top secret value",
            "raw api secret",
            "raw proxy user",
            "raw session secret",
        ):
            self.assertNotIn(secret, rendered)
        self.assertIn("next=visible", rendered)

    def test_every_log_event_has_normalized_minimum_schema(self):
        with tempfile.TemporaryDirectory() as directory:
            logger = get_download_logger(Path(directory))
            log_download_event(logger, "batch_created", batch_id="batch")
            for handler in logger.handlers:
                handler.flush()
            payload = json.loads(
                (Path(directory) / "downloader.jsonl").read_text(encoding="utf-8")
            )
            for handler in logger.handlers:
                handler.close()

        expected = {
            "timestamp",
            "event",
            "batch_id",
            "task_id",
            "attempt_number",
            "platform",
            "media_type",
            "audio_format",
            "speed_mode",
            "elapsed_seconds",
            "status",
            "error_code",
        }
        self.assertTrue(expected.issubset(payload))

    def test_logger_uses_ten_mib_and_five_backups(self):
        with tempfile.TemporaryDirectory() as directory:
            logger = get_download_logger(Path(directory))
            handler = logger.handlers[0]

            self.assertEqual(handler.maxBytes, 10 * 1024 * 1024)
            self.assertEqual(handler.backupCount, 5)
            handler.close()

    def test_unwritable_log_directory_does_not_break_download_flow(self):
        buffer = io.StringIO()
        with (
            patch("download_logging.Path.mkdir", side_effect=OSError("denied")),
            contextlib.redirect_stdout(buffer),
        ):
            logger = get_download_logger(Path("/unwritable"))

        self.assertIsNone(logger)
        self.assertFalse(log_download_event(logger, "started", task_id="task"))
        self.assertIn("下载任务将继续执行", buffer.getvalue())


if __name__ == "__main__":
    unittest.main()
