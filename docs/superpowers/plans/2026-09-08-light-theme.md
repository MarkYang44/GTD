# Dark / light Petronas theme

User request: add a light Apple-style theme with Petronas green accents, selected with a slider; existing dark theme remains default. Preserve editorial fonts, motion, navigation alignment and download functionality.

- [x] Shared early theme bootstrap: gtd_theme_v1 storage, invalid/blocked storage defaults dark, checkbox/switch semantics, cross-tab persistence, no first-paint wrong theme. Shared bilingual control on four pages.
- [x] Add light palette after refined.css: white and soft gray-green surfaces, dark readable text, Petronas green buttons/accents, darker green text links for contrast, adapted fields/status/error/code/table/history/LMU cards. Keep images and image-overlay caption colors unchanged. Header accommodates both controls on mobile.
- [x] Browser verification: default dark, switch/persistence/navigation/cross-tab, blocked storage, language coexistence, both palettes across four routes at desktop/mobile widths, matched LMU navigation positions. Full unit/Node/browser suite, visual check, scoped local commit.

Validation: 420 unit/Node tests passed (2 platform skips); 12 browser tests passed, including 320px/375px/1280px light layout, default dark, persistence, cross-tab switching, and mobile guide anchor clearance. Native Chrome visual QA confirmed desktop light homepage and 375px light homepage/circuit guide. Review identified the mobile anchor offset, now corrected and covered by a browser regression. No backend or dependency changes.
