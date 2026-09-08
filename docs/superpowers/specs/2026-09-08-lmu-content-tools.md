# LMU content tools

User selected the LMU expansion: circuit search, car filtering, favorites and side-by-side recommendation comparison. Extend the current route and content; retain theme, bilingual UI, editorial typography, disclosure animation, image identity and aligned LMU navigation.

Use progressive enhancement on server-rendered cards. A compact toolbar after the guide hero searches English names, slugs, Chinese names/aliases and bilingual locations. Class and car dropdowns filter recommendations; circuits with no matching recommendations disappear. Clear filters restores the list without erasing favorites or comparison selections. Show counts and an empty state.

Allow favorites for circuits and cars, persisted by stable slugs in localStorage. Favorites view selects all / favorite circuits / favorite cars, combined with search and class/car filters. A favorite car is reflected everywhere it occurs. Bad or blocked storage must not break browsing; show when persistence is unavailable and sync favorites across tabs.

Each recommendation can join a comparison selection identified by circuit slug + car slug. Up to three distinct recommendation contexts, including the same car at different circuits, can be selected. Preserve selections while filtering; expose selected items and clear controls. A dialog compares at least two recommendations side by side using existing name, image, class, circuit, recommendation fit, strengths, cautions and official links. No invented rankings or performance data. Small screens horizontally scroll the comparison; keyboard/Escape and focus restoration work. Comparison selection is session-only.

No backend/database/external dependencies are needed. Reuse existing content; add bilingual circuit-name aliases only for search. With JavaScript unavailable, keep the entire read-only guide usable and hide interactive tools.

Verify compound filters, default view, clear/empty state, persistent/global favorites, storage failure, compare limit/context/removal, dialog focus, language/theme, mobile overflow and disclosure behavior. Existing downloads and navigation tests must remain green. Update bilingual README and commit locally; no push.
