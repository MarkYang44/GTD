import importlib.util
import unittest
import re
from dataclasses import replace
from html.parser import HTMLParser
from html import unescape
from tempfile import TemporaryDirectory
from pathlib import Path
from unittest.mock import patch

import lmu_guide_data as guide
import app as web_app

CSS_PATH = Path("static/css/kozekilmu_tracks.css")
HAN = re.compile(r"[\u3400-\u9fff]")


class _EnglishVisibleCopyParser(HTMLParser):
    VOID_ELEMENTS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
    ENGLISH_METADATA_ATTRIBUTES = {
        "data-title-en",
        "data-i18n-alt-en",
        "data-i18n-aria-label-en",
    }

    def __init__(self):
        super().__init__()
        self.stack = []
        self.han_text = []
        self.english_metadata = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        self.english_metadata.extend(
            (name, value)
            for name, value in attributes.items()
            if name in self.ENGLISH_METADATA_ATTRIBUTES
        )
        if tag not in self.VOID_ELEMENTS:
            self.stack.append((tag, attributes))

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                del self.stack[index:]
                return

    def handle_data(self, data):
        if not HAN.search(data):
            return
        if any(tag in {"head", "script", "style"} for tag, _ in self.stack):
            return
        if any(attrs.get("data-guide-copy") == "zh" for _, attrs in self.stack):
            return
        self.han_text.append(" ".join(data.split()))



class LmuGuideParserTests(unittest.TestCase):
    def test_english_copy_parser_treats_param_as_void(self):
        parser = _EnglishVisibleCopyParser()
        parser.feed("<param>")

        self.assertEqual(parser.stack, [])


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
    def test_all_english_guide_data_is_han_free(self):
        english = []
        for car in guide.CARS.values():
            english.extend((car.name, car.car_class, car.strength, car.caution))
        for circuit in guide.CIRCUITS:
            english.extend((circuit.name, circuit.location, circuit.character, circuit.challenge, circuit.advice))
            english.extend(item.fit for item in (*circuit.lmgt3, *circuit.hypercar))
        self.assertEqual([value for value in english if HAN.search(value)], [])

    def test_every_guide_entry_has_complete_chinese_copy(self):
        for car in guide.CARS.values():
            with self.subTest(car=car.slug):
                self.assertTrue(car.strength_zh.strip())
                self.assertTrue(car.caution_zh.strip())

        for circuit in guide.CIRCUITS:
            with self.subTest(circuit=circuit.slug):
                self.assertTrue(circuit.location_zh.strip())
                self.assertIn(f"（{circuit.location}）", circuit.location_zh)
                self.assertTrue(circuit.character_zh.strip())
                self.assertTrue(circuit.challenge_zh.strip())
                self.assertTrue(circuit.advice_zh.strip())
                for recommendation in (*circuit.lmgt3, *circuit.hypercar):
                    self.assertTrue(recommendation.fit_zh.strip())

    def test_data_validation_rejects_blank_chinese_copy(self):
        invalid = replace(guide.CIRCUITS[0], advice_zh="")
        with patch.object(guide, "CIRCUITS", (invalid, *guide.CIRCUITS[1:])):
            with self.assertRaisesRegex(ValueError, "blank circuit copy"):
                guide.validate_guide_data()

    def test_chinese_copy_keeps_selected_technical_terms_bilingual(self):
        copy = " ".join(
            (
                *(car.strength_zh + " " + car.caution_zh for car in guide.CARS.values()),
                *(circuit.character_zh + " " + circuit.challenge_zh + " " + circuit.advice_zh for circuit in guide.CIRCUITS),
            )
        )
        for term in ("制动稳定性（braking stability）", "轮胎负荷（tyre load）"):
            self.assertIn(term, copy)

    def test_chinese_copy_preserves_specific_fit_details_and_low_drag(self):
        circuits = {circuit.slug: circuit for circuit in guide.CIRCUITS}
        fits = [
            recommendation
            for circuit in guide.CIRCUITS
            for recommendation in (*circuit.lmgt3, *circuit.hypercar)
        ]
        barcelona_porsche = next(
            item for item in (*circuits["barcelona"].lmgt3, *circuits["barcelona"].hypercar)
            if item.car_slug == "porsche-911-gt3-r"
        )
        barcelona_peugeot = next(
            item for item in circuits["barcelona"].hypercar
            if item.car_slug == "peugeot-9x8-2024"
        )
        le_mans_ferrari = next(
            item for item in circuits["le-mans"].hypercar
            if item.car_slug == "ferrari-499p"
        )

        self.assertEqual(
            barcelona_porsche.fit_zh,
            "后置引擎的牵引力有助于应对负荷弯后的技术性末段。",
        )
        self.assertEqual(
            barcelona_peugeot.fit_zh,
            "灵活的空气动力学套件对 Barcelona 的混合型末段响应良好。",
        )
        self.assertEqual(
            le_mans_ferrari.fit_zh,
            "空气动力学性能适合勒芒的低阻力与高速需求。",
        )
        self.assertIn("低阻力", circuits["le-mans"].character_zh)
        self.assertNotIn("低下压力", circuits["le-mans"].character_zh)
        self.assertEqual(len({item.fit_zh for item in fits}), 96)
        self.assertFalse(any("可应对" in item.fit_zh for item in fits))

    def test_portimao_throttle_advice_is_natural_and_not_self_contradictory(self):
        portimao = next(circuit for circuit in guide.CIRCUITS if circuit.slug == "portimao")

        self.assertEqual(
            portimao.advice_zh,
            "在盲顶使用可重复的参考点，等车身稳定后再加油。",
        )
        self.assertNotIn("再延后加油", portimao.advice_zh)

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

    def test_blank_image_paths_are_valid_optional_metadata(self):
        blank_car = replace(guide.CARS["bmw-m4-lmgt3"], image="")
        blank_circuit = replace(guide.CIRCUITS[0], image="")

        with patch.object(guide, "CARS", {**guide.CARS, blank_car.slug: blank_car}), patch.object(
            guide,
            "CIRCUITS",
            (blank_circuit, *guide.CIRCUITS[1:]),
        ):
            guide.validate_guide_data()

    def test_unsafe_configured_image_path_is_rejected(self):
        unsafe_circuit = replace(guide.CIRCUITS[0], image="../../outside.webp")

        with patch.object(guide, "CIRCUITS", (unsafe_circuit, *guide.CIRCUITS[1:])):
            with self.assertRaisesRegex(ValueError, "non-local circuit image"):
                guide.validate_guide_data()


class LmuGuideRouteTests(unittest.TestCase):
    def setUp(self):
        self.client = web_app.app.test_client()

    def test_english_visible_body_has_no_han_copy(self):
        parser = _EnglishVisibleCopyParser()
        parser.feed(self.client.get("/kozekilmu/tracks").get_data(as_text=True))
        self.assertEqual(parser.han_text, [])

    def test_image_availability_reflects_runtime_static_file_changes(self):
        relative_path = "kozekilmu/guide/tracks/runtime-image.webp"
        with TemporaryDirectory() as directory:
            static_root = Path(directory)
            image_path = static_root / relative_path
            with patch.object(web_app.app, "_static_folder", str(static_root)):
                self.assertFalse(web_app._guide_static_image_exists(relative_path))
                image_path.parent.mkdir(parents=True)
                image_path.write_bytes(b"image")
                self.assertTrue(web_app._guide_static_image_exists(relative_path))
                image_path.unlink()
                self.assertFalse(web_app._guide_static_image_exists(relative_path))

    def test_tracks_route_renders_circuit_guide(self):
        response = self.client.get("/kozekilmu/tracks")
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("<title>LMU 赛道指南 - GTD</title>", html)
        self.assertIn('href="/kozekilmu"', html)
        self.assertIn('href="/kozekilmu/tracks"', html)
        self.assertIn('href="/kozekilmu/tracks" aria-current="page"', html)
        self.assertEqual(html.count('class="circuit-card"'), 16)
        self.assertEqual(html.count("<details"), 16)
        self.assertEqual(html.count('data-class="LMGT3"'), 48)
        self.assertEqual(html.count('data-class="Hypercar"'), 48)

    def test_circuit_reveal_stagger_is_bounded_per_grid_row(self):
        html = self.client.get("/kozekilmu/tracks").get_data(as_text=True)
        cards = re.findall(r'<article class="circuit-card"[^>]*>', html)
        self.assertEqual(len(cards), 16)
        self.assertTrue(all('data-motion-group="lmu-circuits"' in card for card in cards))
        orders = [re.search(r'data-motion-order="(\d+)"', card).group(1) for card in cards]
        self.assertEqual(orders, [str(index % 2) for index in range(16)])
        self.assertLessEqual(max(map(int, orders)), 1)

    def test_blank_and_missing_circuit_images_render_placeholders_without_static_urls(self):
        missing_image_circuit = replace(
            guide.CIRCUITS[0],
            image="kozekilmu/guide/tracks/missing-for-qa.webp",
        )
        blank_image_circuit = replace(guide.CIRCUITS[1], image="")
        with patch.object(
            web_app,
            "CIRCUITS",
            (missing_image_circuit, blank_image_circuit, *guide.CIRCUITS[2:]),
        ):
            html = self.client.get("/kozekilmu/tracks").get_data(as_text=True)

        self.assertIn('aria-label="Bahrain 暂无官方赛道图片"', html)
        self.assertIn('aria-label="Circuit de Barcelona-Catalunya 暂无官方赛道图片"', html)
        self.assertNotIn("missing-for-qa.webp", html)

    def test_blank_and_missing_car_images_render_placeholders_without_static_urls(self):
        missing_car = replace(
            guide.CARS["bmw-m4-lmgt3"],
            image="kozekilmu/guide/cars/missing-for-qa.webp",
        )
        blank_car = replace(guide.CARS["corvette-z06-lmgt3-r"], image="")
        with patch.object(
            web_app,
            "CARS",
            {**guide.CARS, missing_car.slug: missing_car, blank_car.slug: blank_car},
        ):
            html = self.client.get("/kozekilmu/tracks").get_data(as_text=True)

        self.assertIn('aria-label="BMW M4 LMGT3 暂无官方车型图片"', html)
        self.assertIn('aria-label="Corvette Z06 LMGT3.R 暂无官方车型图片"', html)
        self.assertNotIn("missing-for-qa.webp", html)

    def test_guide_never_renders_inline_image_error_handlers(self):
        html = self.client.get("/kozekilmu/tracks").get_data(as_text=True)

        self.assertNotIn("onerror=", html)
        self.assertNotIn("onerror=", Path("templates/kozekilmu_tracks.html").read_text(encoding="utf-8"))

    def test_guide_reuses_the_victory_topbar_and_download_return_link(self):
        html = self.client.get("/kozekilmu/tracks").get_data(as_text=True)
        css = CSS_PATH.read_text(encoding="utf-8")

        self.assertIn('<header class="topbar" id="topbar" data-lmu-layout>', html)
        self.assertIn('class="topbar-link" href="/#task-card">', html)
        self.assertIn('<span data-guide-copy="zh">返回下载</span>', html)
        self.assertIn('class="service-status"', html)
        self.assertIn('aria-label="Kozeki Ui"', html)
        self.assertIn('.topbar.is-scrolled', css)
        self.assertIn('height: 68px', css)
        self.assertIn('width: min(1180px, calc(100% - 40px))', css)

    def test_guide_server_renders_chinese_default_and_complete_language_control(self):
        html = self.client.get("/kozekilmu/tracks").get_data(as_text=True)
        rendered_copy = unescape(html)

        self.assertIn('<html lang="zh-CN" data-guide-language="zh"', html)
        self.assertIn('id="guide-language-toggle"', html)
        self.assertIn('type="checkbox"', html)
        self.assertIn('data-guide-copy="zh"', html)
        self.assertIn('data-guide-copy="en"', html)
        self.assertIn("LMU 赛道指南", html)
        self.assertIn("LMU Circuit Guide", html)
        self.assertIn(guide.CIRCUITS[0].character_zh, rendered_copy)
        self.assertIn(guide.CIRCUITS[0].character, rendered_copy)
        self.assertIn(guide.CIRCUITS[0].lmgt3[0].fit_zh, rendered_copy)
        self.assertIn(guide.CIRCUITS[0].lmgt3[0].fit, rendered_copy)

    def test_topbar_brand_stays_english_and_updated_label_is_bilingual(self):
        html = self.client.get("/kozekilmu/tracks").get_data(as_text=True)

        self.assertIn('<div class="brand">Designed by Mark Yang</div>', html)
        self.assertNotIn("由 Mark Yang 设计", html)
        self.assertIn(
            '<span data-guide-copy="en">Updated: </span><time',
            html,
        )

    def test_language_metadata_covers_dynamic_accessible_attributes(self):
        html = self.client.get("/kozekilmu/tracks").get_data(as_text=True)

        self.assertIn('data-title-zh="LMU 赛道指南 - GTD"', html)
        self.assertIn('data-title-en="LMU Circuit Guide - GTD"', html)
        self.assertIn('data-i18n-alt-zh="Bahrain 赛道"', html)
        self.assertIn('data-i18n-alt-en="Bahrain circuit"', html)
        self.assertIn('data-i18n-aria-label-zh=', html)
        self.assertIn('data-i18n-aria-label-en=', html)

    def test_rendered_english_metadata_is_complete_and_han_free(self):
        parser = _EnglishVisibleCopyParser()
        parser.feed(self.client.get("/kozekilmu/tracks").get_data(as_text=True))

        self.assertTrue(parser.english_metadata)
        self.assertEqual(
            {name for name, _ in parser.english_metadata},
            parser.ENGLISH_METADATA_ATTRIBUTES,
        )
        for name, value in parser.english_metadata:
            with self.subTest(attribute=name, value=value):
                self.assertTrue(value and value.strip())
                self.assertIsNone(HAN.search(value))

    def test_every_dynamic_accessible_attribute_has_both_language_variants(self):
        html = self.client.get("/kozekilmu/tracks").get_data(as_text=True)
        translated_tags = [
            tag
            for tag in re.findall(r"<[^>]+>", html)
            if "data-i18n-alt-" in tag or "data-i18n-aria-label-" in tag
        ]

        self.assertTrue(translated_tags)
        for tag in translated_tags:
            with self.subTest(tag=tag[:120]):
                for attribute in ("alt", "aria-label"):
                    if f"data-i18n-{attribute}-" in tag:
                        self.assertIn(f"data-i18n-{attribute}-zh=", tag)
                        self.assertIn(f"data-i18n-{attribute}-en=", tag)

    def test_language_control_order_footer_and_no_inline_script_contract(self):
        html = self.client.get("/kozekilmu/tracks").get_data(as_text=True)
        template = Path("templates/kozekilmu_tracks.html").read_text(encoding="utf-8")

        toggle_position = html.index('class="language-toggle"')
        return_position = html.index('class="topbar-link"')
        avatar_position = html.index('class="service-status"')
        self.assertLess(toggle_position, return_position)
        self.assertLess(return_position, avatar_position)
        self.assertIn(
            '<span data-guide-copy="zh" lang="zh-CN">中文</span>'
            '<span data-guide-copy="en">ZH</span>',
            html,
        )
        self.assertIn("资料来源：", html)
        self.assertIn("车型建议反映", html)
        self.assertIn("Sources:", html)
        self.assertIn("Recommendations reflect public game content", html)
        self.assertNotRegex(template, r"<script(?![^>]*\bsrc=)")
        self.assertNotRegex(template, r"\bon[a-z]+\s*=")


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
        self.assertIn('width="1024"', html)
        self.assertIn('height="576"', html)
        self.assertEqual(html.count("data-motion-surface"), 16)
        self.assertEqual(html.count('data-motion-sheen aria-hidden="true"'), 16)
        self.assertIn("Balance of Performance（BoP）或物理版本更新后可能变化", html)
        self.assertIn('href="https://lemansultimate.com/circuits/"', html)
        self.assertIn('href="https://lemansultimate.com/cars/"', html)

    def test_language_slider_css_is_responsive_accessible_and_fail_open(self):
        css = CSS_PATH.read_text(encoding="utf-8")

        self.assertIn('html[data-guide-language="zh"] [data-guide-copy="zh"]', css)
        self.assertIn('html[data-guide-language="en"] [data-guide-copy="en"]', css)
        self.assertRegex(css, r"(?s)\.language-toggle\s*\{[^}]*min-height:\s*44px")
        self.assertIn(".language-toggle input:focus-visible", css)
        self.assertRegex(css, r"@media\s*\(max-width:\s*560px\)")
        reduced_motion_start = css.find("@media (prefers-reduced-motion: reduce)")
        self.assertNotEqual(reduced_motion_start, -1)
        self.assertNotIn("display: none", css[reduced_motion_start:])

    def test_bilingual_navigation_copy_is_not_offset_as_a_single_wrapper(self):
        css = CSS_PATH.read_text(encoding="utf-8")

        self.assertNotIn(".easter-nav-link span {", css)

    def test_compact_topbar_keeps_language_controls_unshrunk_at_390px(self):
        css = CSS_PATH.read_text(encoding="utf-8")
        compact_start = css.find("@media (max-width: 440px)")

        self.assertGreaterEqual(compact_start, 0)
        compact_end = css.find("@media", compact_start + 1)
        compact_block = css[compact_start:compact_end]
        self.assertRegex(compact_block, r"(?s)\.brand\s*\{[^}]*display:\s*none")
        self.assertRegex(
            compact_block,
            r"(?s)\.topbar-inner\s*\{[^}]*justify-content:\s*flex-end",
        )
        self.assertRegex(
            compact_block,
            r"(?s)\.topbar-actions\s*\{[^}]*width:\s*100%[^}]*justify-content:\s*flex-end",
        )
        self.assertRegex(
            compact_block,
            r"(?s)\.language-toggle,\s*\.topbar-link,\s*\.service-status\s*\{[^}]*flex:\s*0 0 auto",
        )
        self.assertRegex(css, r"(?s)\.topbar-link\s*\{[^}]*white-space:\s*nowrap")

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
