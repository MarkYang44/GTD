# LMU catalog and strategy implementation

Authorized scope: car catalog and pre-race fuel estimator, using existing bilingual/theme/navigation architecture. No new racing claims or external data.

1. Catalog: reuse CARS/CIRCUITS, shared guide shell, toolbar/favorites/comparison runtime. Derive reverse circuit recommendations from canonical data. Shared favorites must preserve all valid circuit and car IDs across pages. Catalog compares cars with their strengths, caveats, and circuit recommendations; selections remain page-local.
2. Navigation: one partial across LMU pages, preserving existing first two links; append catalog and strategy links. Keep existing shared alignment.
3. Strategy: independent route using the guide shell. Empty inputs default to 30 min, 120 sec/lap, 3 L/lap. Estimate timed laps as ceil(duration seconds / lap seconds), add one extra lap, reserve max(10% of planned fuel, one lap fuel), round total up to 0.1 L. Explain default assumptions and manual adjustment; no tank capacity/pit-stop simulation. Invalid nonempty input must show errors rather than silently default. Accept lap seconds or m:ss.
4. Verify: pure calculator boundary tests; real browser tests for routes, cross-page favorites preservation, catalog filtering/comparison, strategy defaults/invalid input/translation/mobile; existing regression suite.
5. Update bilingual README/web guide, review diff and save local commit, no push.

## Completion evidence

- Implemented both routes, shared navigation, and catalog mode in the existing guide/runtime. Canonical CARS/CIRCUITS remain unchanged; all 16 cataloged cars are shown.
- Favorites sanitize against the full catalog on both pages, preserving circuit favorites when saving from the car catalog. Comparison retains each car's reverse circuit recommendation list.
- Calculator handles defaults, m:ss parsing, invalid inputs, rounding boundaries, minimum reserve, and partial default use. No dependencies or remote services added.
- 431 unit/Node tests passed (2 platform skips); 22 browser tests passed. Native Chrome visual review of catalog and strategy confirmed existing editorial typography, shared navigation, light theme, and green accents. Bilingual README and web guide updated.
