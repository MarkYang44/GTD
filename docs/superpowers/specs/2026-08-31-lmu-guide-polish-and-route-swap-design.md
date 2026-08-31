# LMU Guide Reveal, Language Purity, and Route Swap Design

## Goal

Polish the bilingual LMU easter-egg pages without changing downloader behavior or the established visual theme:

1. Circuit cards must reveal promptly even when the user scrolls quickly.
2. English mode must expose English-only visible copy; Chinese mode may retain English proper nouns or bilingual technical terms.
3. The task mascot must open the circuit guide first by swapping the two existing page routes.

## Confirmed approach

Use the approved A/A/A approach: page-local reveal ordering, semantic dual-language copy with automated purity checks, and a true route-content swap.

## Reveal performance

### Root cause

Every circuit card currently uses the shared motion runtime's default reveal group. The runtime assigns increasing orders across all 16 cards. CSS applies `order * 70ms` plus a 680ms entrance transition, so a lower card can remain invisible for roughly 1.7 seconds after intersecting the viewport.

### Change

Keep `data-motion-reveal` and the surface effect, but give circuit cards an LMU-specific group and a row-local order (`loop.index0 % 2`). In the two-column layout, the left card enters immediately and the right card is delayed only 70ms. In the one-column layout, the same bounded delay remains harmless. Do not change the shared motion runtime or other pages.

### Contract

- No circuit card receives an order greater than 1.
- The existing 680ms animation remains.
- Reduced-motion and fail-open behavior remain unchanged.

## English-only mode

### Current evidence

All English fields in `lmu_guide_data.py` are free of Han characters. The bilingual branch already wraps the source links and caution text correctly. The only visible Han text outside a Chinese copy wrapper is the language-control label `中文`.

### Change

- Render the language label as `中文` in Chinese mode and `ZH` in English mode.
- Keep English source links, notices, car cautions, footer, title, alt text, and ARIA labels fully English.
- Chinese mode may use English circuit/car names and parenthetical English technical terms where useful.
- Add an automated rendered-body audit so Han text cannot leak into English-visible nodes. Ignore the Chinese copy branch and language metadata that the runtime intentionally keeps for switching.
- Add a data audit confirming every English car, circuit, and recommendation field remains free of Han characters.

## Route swap

Swap the content served by the two existing endpoints while preserving both URLs:

| URL | New content |
| --- | --- |
| `/kozekilmu` | Circuit guide |
| `/kozekilmu/tracks` | Victory archive |

The homepage mascot already links to `/kozekilmu`, so it will open the circuit guide without changing the public entry URL. Update both page navigation bars so labels, active state, and `aria-current` match the new destinations. Update Flask docstrings and route tests. No new route or redirect is introduced.

## Scope and compatibility

- Preserve all downloader, queue, conversion, cookie, and API behavior.
- Preserve the two page templates, their styles, and existing assets.
- Do not modify the shared motion algorithm.
- Keep old bookmarks valid; only which of the two easter-egg pages they display changes, as explicitly requested.
- No new dependency.

## Verification

Use tests-first changes to cover:

1. Circuit-card reveal orders are bounded to `0/1` and the shared runtime is unchanged.
2. English-visible rendered body contains no Han text; English data fields also contain none.
3. Chinese mode retains the approved bilingual/proper-noun copy.
4. `/kozekilmu` renders the circuit guide and `/kozekilmu/tracks` renders the victory archive.
5. Homepage mascot, both navigation bars, active state, and ARIA point to the swapped destinations.
6. Focused LMU/motion tests, the full unittest suite, Python compile checks, JavaScript syntax/harness, and `git diff --check` pass.
7. If browser control remains unavailable, report responsive visual checks as an explicit limitation rather than claiming screenshots.
