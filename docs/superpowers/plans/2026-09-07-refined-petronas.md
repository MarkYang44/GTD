# Refined Petronas Implementation Plan

> **For agentic workers:** Use subagent-driven-development for the bounded motion task; primary implements shared presentation and integration.

**Goal:** A quieter four-page dark interface with unchanged Petronas green identity.
**Architecture:** Shared final CSS layer for visual tokens/components; explicit calm motion profile reuses existing lifecycle and accessibility fallbacks.
**Tech Stack:** Flask/Jinja, plain CSS/JS, unittest, Chromium/Playwright.

## Global Constraints
- Preserve #009b95 / #00a19b theme, exact branding, routes and assets.
- No new dependencies or download behavior changes. Retain Chinese/English switching.
- Current approved local checkout; local final commit, no push.

## Task 1: Calm motion
- [x] Add failing behavioral regression: calm profile never installs pointer tilt handlers or changes parallax offsets.
- [x] In static/js/motion.js, detect root.dataset.motionProfile === 'calm'; bypass pointer and parallax work for that profile while preserving reveal/lifecycle/number updates and legacy opt-in behavior.
- [x] In static/css/motion.css, calm profile uses 280ms opacity/6px movement with 35ms capped stagger; no filter blur. Retain reduced-motion overrides.
- [x] Run tests/test_motion_system.py and new regression.

## Task 2: Shared presentation
- [x] Add static/css/refined.css last in all four template heads, root data-motion-profile="calm". Define common color/font/radius/spacing tokens and consistent navigation, controls and surface treatments.
- [x] Remove presentation motion markers from homepage download workspace, cards and task panel so forms never fade/tilt. Keep content entrances elsewhere.
- [x] Reduce homepage hero to 40-64px title, 40px vertical padding and compact metrics. Hide orbital ornament. Keep signature, imagery and bilingual text intact.
- [x] Add browser checks for computed typography/green accent, stable form hover, no blur, mobile document width, all four routes and reduced motion.

## Task 3: Verify and commit
- [x] Run unittest discover tests, all Node harnesses, JS syntax checks and browser suite in the existing temporary clean baseline environment.
- [x] Inspect actual browser rendering; correct layout issues, run relevant checks again.
- [x] Independent code review; update this record with evidence. Commit scoped files locally.

## Final verification — 2026-09-08

User amendment: restore original editorial type in supplied screenshot regions, including homepage hero/metrics/footer, LMU heroes and circuit names/card text. Keep system UI type for forms and user-guide text. Original Cormorant Garamond italic and Palatino UI Italic stacks are reused; Petronas green remains #009b95/#00a19b.

- Full Python suite: 418 tests, OK (2 existing platform skips).
- Chromium regression suite: 6 tests, OK. Covers four routes at 1280px and 375px in both languages, expected editorial vs control typography, brand colors, document/header bounds, stable immediately available forms, reduced-motion readability and existing preview/history behavior.
- All four Node harnesses, production JS syntax checks and git diff --check passed.
- Native Chrome visual checks: refined desktop homepage/forms, iPhone SE download form and circuit page on September 7; restored editorial homepage and English circuit card names on September 8. Final mobile two-column nav covered by browser layout suite; September 7 final native reload was blocked by exhausted tool quota, subsequent native checks resumed successfully.
- Independent review found no blocking regressions; rank typography was aligned with the amended editorial preference.
- No downloader/API changes or dependency changes. Hosted CI and live media downloads were not run for this presentation change.
