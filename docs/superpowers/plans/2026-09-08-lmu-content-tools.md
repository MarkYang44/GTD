# LMU content tools implementation plan

Use subagent-driven-development for independent runtime work and parent template/CSS/browser integration.

- [x] Shared contract: card data attributes and comparison source templates; toolbar, favorites buttons, comparison dialog; graceful no-JS behavior.
- [x] Runtime: normalized search and compound filtering, favorites storage/cross-tab, three-context comparison, language updates, focus and empty states.
- [x] Verify browser flows against existing local content, unit/source regressions and disclosure/navigation compatibility; review implementation.
- [x] Update bilingual README and web guide, record validation; ready for local commit.

Validation: 428 unit/Node tests completed successfully (2 platform skips); 18 browser tests passed. Browser coverage includes mobile/light theme, language changes, persistent/cross-tab favorites, blocked storage, compound filtering, comparison limits and removal, keyboard focus, and no-JS fallback. Independent review identified focus loss when another tab removes the focused favorite; fixed and covered by regression. Native Chrome visual inspection confirmed the light-theme toolbar and two-column comparison dialog preserve the existing editorial titles and green accents. No backend/data/dependency changes.
