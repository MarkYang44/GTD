import importlib.util
import unittest
from dataclasses import replace
from tempfile import TemporaryDirectory
from pathlib import Path
from unittest.mock import patch

import lmu_guide_data as guide
import app as web_app

CSS_PATH = Path("static/css/kozekilmu_tracks.css")


def _load_asset_sync_module():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "sync_lmu_guide_assets.py"
    spec = importlib.util.spec_from_file_location("sync_lmu_guide_assets", script_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


asset_sync = _load_asset_sync_module()


EXPECTED_SLUGS = (
    "bahrain", "barcelona", "le-mans", "paul-ricard", "cota", "daytona",
    "fuji", "imola", "interlagos", "lusail", "monza", "portimao",
    "sebring", "silverstone-international", "spa", "laguna-seca",
)
EXPECTED_DLC = {
    "barcelona", "paul-ricard", "cota", "daytona", "imola",
    "interlagos", "lusail", "silverstone-international", "laguna-seca",
}


class LmuGuideDataTests(unittest.TestCase):
    def test_current_official_circuit_snapshot_is_complete_and_ordered(self):
        self.assertEqual(tuple(item.slug for item in guide.CIRCUITS), EXPECTED_SLUGS)
        self.assertEqual(
            {item.slug for item in guide.CIRCUITS if item.is_dlc},
            EXPECTED_DLC,
        )

    def test_each_circuit_has_three_unique_recommendations_per_requested_class(self):
        for circuit in guide.CIRCUITS:
            with self.subTest(circuit=circuit.slug):
                self.assertEqual(len(circuit.lmgt3), 3)
                self.assertEqual(len(circuit.hypercar), 3)
                self.assertEqual(len({item.car_slug for item in circuit.lmgt3}), 3)
                self.assertEqual(len({item.car_slug for item in circuit.hypercar}), 3)
                self.assertTrue(all(guide.CARS[item.car_slug].car_class == "LMGT3" for item in circuit.lmgt3))
                self.assertTrue(all(guide.CARS[item.car_slug].car_class == "Hypercar" for item in circuit.hypercar))

    def test_copy_and_sources_are_complete_without_fastest_claims(self):
        guide.validate_guide_data()
        forbidden = ("绝对最快", "必胜", "guaranteed fastest")
        for circuit in guide.CIRCUITS:
            copy = " ".join((circuit.character, circuit.challenge, circuit.advice))
            self.assertTrue(circuit.source_url.startswith("https://lemansultimate.com/"))
            self.assertFalse(any(token in copy.lower() for token in forbidden))
            for recommendation in (*circuit.lmgt3, *circuit.hypercar):
                self.assertGreaterEqual(len(recommendation.fit), 12)


class LmuGuideRouteTests(unittest.TestCase):
    def setUp(self):
        self.client = web_app.app.test_client()

    def test_read_only_circuit_guide_renders_all_circuits_and_recommendations(self):
        response = self.client.get("/kozekilmu/tracks")
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("<title>LMU 赛道指南 - GTD</title>", html)
        self.assertIn('href="/kozekilmu"', html)
        self.assertIn('href="/kozekilmu/tracks"', html)
        self.assertIn('aria-current="page"', html)
        self.assertEqual(html.count('class="circuit-card"'), 16)
        self.assertEqual(html.count("<details"), 16)
        self.assertEqual(html.count('data-class="LMGT3"'), 48)
        self.assertEqual(html.count('data-class="Hypercar"'), 48)

    def test_invalid_circuit_image_path_keeps_a_readable_placeholder(self):
        missing_image_circuit = replace(
            guide.CIRCUITS[0],
            image="kozekilmu/guide/tracks/missing-for-qa.webp",
        )
        with patch.object(
            web_app,
            "CIRCUITS",
            (missing_image_circuit, *guide.CIRCUITS[1:]),
        ):
            html = self.client.get("/kozekilmu/tracks").get_data(as_text=True)

        self.assertIn("missing-for-qa.webp", html)
        self.assertIn('aria-label="Bahrain 暂无官方赛道图片"', html)
        self.assertIn("onerror=", html)

class LmuGuidePresentationTests(unittest.TestCase):
    def setUp(self):
        self.client = web_app.app.test_client()

    def test_layout_disclosure_and_reduced_motion_contracts(self):
        css = CSS_PATH.read_text(encoding="utf-8") if CSS_PATH.exists() else ""
        reduced_motion_start = css.find("@media (prefers-reduced-motion: reduce)")
        reduced_motion_block = css[reduced_motion_start:] if reduced_motion_start >= 0 else ""

        self.assertIn("grid-template-columns: repeat(2, minmax(0, 1fr))", css)
        self.assertRegex(css, r"@media\s*\(max-width:\s*820px\)")
        self.assertRegex(
            css,
            r"(?s)\.circuit-grid\s*\{[^}]*grid-template-columns:\s*1fr",
        )
        self.assertIn("prefers-reduced-motion: reduce", css)
        self.assertIn("details[open]", css)
        self.assertIn(":focus-visible", css)
        self.assertIn(".media-placeholder", css)
        self.assertNotIn("display: none", reduced_motion_block)

    def test_media_motion_and_attribution_contracts(self):
        html = self.client.get("/kozekilmu/tracks").get_data(as_text=True)

        self.assertIn('loading="lazy"', html)
        self.assertIn('width="1024" height="576"', html)
        self.assertEqual(html.count("data-motion-surface"), 16)
        self.assertEqual(html.count('data-motion-sheen aria-hidden="true"'), 16)
        self.assertIn("Balance of Performance（BoP）或物理版本更新后可能变化", html)
        self.assertIn('href="https://lemansultimate.com/circuits/"', html)
        self.assertIn('href="https://lemansultimate.com/cars/"', html)

    def test_original_page_uses_matching_responsive_easter_navigation(self):
        html = self.client.get("/kozekilmu").get_data(as_text=True)

        self.assertIn("margin-bottom: clamp(34px, 5vw, 64px)", html)
        self.assertRegex(
            html,
            r"(?s)@media \(max-width: 560px\).*?\.easter-nav-link\s*\{\s*width:\s*100%",
        )


class LmuGuideAssetTests(unittest.TestCase):
    def _assert_local_webp_assets(self, items, resource):
        items = tuple(items)
        image_paths = tuple(item.image for item in items)
        self.assertEqual(len(image_paths), len(set(image_paths)))

        for item in items:
            with self.subTest(resource=resource, image=item.image):
                self.assertTrue(item.source_url.startswith((
                    "https://lemansultimate.com/",
                    "https://lemansultimate.com/wp-content/uploads/",
                )))
                self.assertTrue(item.image_source_url.startswith((
                    "https://lemansultimate.com/",
                    "https://lemansultimate.com/wp-content/uploads/",
                )))
                path = Path("static") / item.image
                self.assertTrue(path.is_file(), item.image)
                self.assertEqual(path.read_bytes()[:4], b"RIFF")
                self.assertEqual(path.read_bytes()[8:12], b"WEBP")
                self.assertLess(path.stat().st_size, 450_000)

    def test_all_circuit_assets_are_local_webp_files(self):
        self._assert_local_webp_assets(guide.CIRCUITS, "tracks")

    def test_all_recommended_car_assets_are_local_webp_files(self):
        recommended_car_slugs = {
            recommendation.car_slug
            for circuit in guide.CIRCUITS
            for recommendation in (*circuit.lmgt3, *circuit.hypercar)
        }
        self._assert_local_webp_assets(
            (guide.CARS[slug] for slug in recommended_car_slugs),
            "cars",
        )


class LmuGuideAssetSyncTests(unittest.TestCase):
    def test_detects_a_libwebp_capable_ffmpeg(self):
        with patch.object(asset_sync.subprocess, "run", return_value=type("Result", (), {"stdout": " libwebp WebP image"})()) as run:
            self.assertTrue(asset_sync._ffmpeg_supports_libwebp("ffmpeg"))

        run.assert_called_once_with(
            ["ffmpeg", "-hide_banner", "-encoders"],
            capture_output=True,
            check=True,
            text=True,
        )

    def test_uses_existing_cwebp_when_ffmpeg_lacks_libwebp(self):
        with TemporaryDirectory() as directory:
            temporary_path = Path(directory)
            source_path = temporary_path / "source.png"
            output_path = temporary_path / "output.webp"
            with patch.object(asset_sync, "_ffmpeg_supports_libwebp", return_value=False), patch.object(asset_sync.subprocess, "run") as run:
                asset_sync._convert_to_webp(
                    source_path,
                    output_path,
                    temporary_path,
                    "ffmpeg",
                    "cwebp",
                )

        self.assertEqual(
            [call.args[0] for call in run.call_args_list],
            [
                [
                    "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                    "-i", str(source_path), "-vf",
                    "scale=1024:576:force_original_aspect_ratio=decrease",
                    "-frames:v", "1", str(temporary_path / "source.resized.png"),
                ],
                [
                    "cwebp", "-quiet", "-q", "82", "-m", "6",
                    str(temporary_path / "source.resized.png"), "-o", str(output_path),
                ],
            ],
        )
