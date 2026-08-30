# LMU Circuit Guide Bilingual Toggle Design

## Goal

Add complete Chinese and English presentation modes to `/kozekilmu/tracks`
without changing downloader behavior, reloading the page, or disturbing the
current LMU guide layout and motion system.

The first visit uses Chinese. Later visits restore the user's most recently
selected language. Chinese copy may include an English term in parentheses
when that improves the precision of motorsport terminology.

## Scope

The language switch covers every user-facing string on the circuit-guide page:

- browser title and document language;
- topbar, page navigation, hero, update label, and section labels;
- circuit descriptions, challenges, advice, image alternatives, and source
  links;
- recommendation disclosure controls, car recommendations, strengths,
  cautions, and image alternatives;
- footer source attribution and BoP/version disclaimer.

Official circuit names, car names, `LMGT3`, `Hypercar`, `DLC`, `LMU`, and `BoP`
remain unchanged. The victory archive at `/kozekilmu` is outside this change.

## User Interface

The topbar action order becomes:

1. a compact `中文 — EN` slider;
2. the return-to-download link;
3. the Kozeki Ui avatar.

The control is a native checkbox styled as a slider. Its label and accessible
state make the two language choices understandable to keyboard and screen-reader
users. It retains a visible focus state and a touch target of at least 44px.

Switching language:

- updates the page immediately without navigation or reload;
- preserves scroll position and every open `<details>` element;
- updates the browser title, `lang` attribute, visible copy, image `alt` text,
  relevant `aria-label` values, and the control state;
- preserves the existing two-column/one-column responsive behavior and shared
  reveal, tilt, sheen, and reduced-motion contracts.

Below 560px, the slider becomes more compact but remains beside the return link
and avatar without causing horizontal overflow.

## Content Model

Existing English fields remain the canonical English interface. Matching
Chinese companion fields are added only where copy is translated:

- `Car`: Chinese strength and caution;
- `Recommendation`: Chinese fit explanation;
- `Circuit`: Chinese location, character, challenge, and advice.

The current English field names and official names/URLs remain unchanged to
avoid breaking existing callers and tests. Static UI translations live in the
template because they are page chrome rather than guide data.

`validate_guide_data()` must require both language versions for every translated
field while preserving all existing constraints: 16 ordered circuits, unique
slugs, local image rules, official LMU URLs, and exactly three unique
recommendations for each requested class.

Chinese translations favor natural motorsport language over literal wording.
Chinese locations retain the original location in parentheses, for example
`萨基尔，巴林（Sakhir, Bahrain）`. When a motorsport term could be ambiguous,
the Chinese copy includes the English form once, for example
`制动稳定性（braking stability）` or `轮胎负荷（tyre load）`.

## Rendering and State Flow

The server renders both language variants so the feature works offline and does
not require a translation service or another API request. The root element starts
with `lang="zh-CN"` and a Chinese language-state attribute. CSS hides only the
inactive language variant with `display: none`, so hidden copy is also removed
from the accessibility tree.

A dedicated `static/js/lmu_guide_language.js` owns language behavior. It does
not modify `static/js/motion.js` and no inline JavaScript is added.

Initialization flow:

1. read a guide-specific `localStorage` value;
2. accept only `zh` or `en`;
3. otherwise select `zh`;
4. apply the root language state, browser title, translated attributes, and
   slider state;
5. on slider change, apply the selected language and attempt to persist it.

Storage reads and writes are guarded. If storage is unavailable, malformed, or
throws, the page remains usable and defaults to Chinese. The feature never
depends on network access after the page loads.

## Accessibility and Failure Behavior

- With JavaScript disabled or failed, Chinese remains visible and the guide is
  fully readable.
- The slider is keyboard operable, visibly focusable, and exposes its checked
  state through native semantics.
- No bilingual duplicates are simultaneously exposed to assistive technology.
- Existing native `<details>/<summary>` behavior is preserved.
- Image fallback logic remains server-side and unchanged.
- Reduced-motion mode changes no language content and does not hide the switch.

## Testing

Implementation follows red-green-refactor.

Data and route tests will verify:

- every translated field is non-empty in both languages;
- Chinese is the server-rendered default;
- all visible page regions contain both variants where required;
- official names, URLs, recommendation counts, image fallback, topbar, and
  downloader routes remain unchanged;
- the page loads only the shared motion runtime plus the dedicated language
  script and contains no inline event handlers.

JavaScript behavior tests will use a small DOM/storage harness to verify:

- first visit defaults to Chinese;
- a stored English choice is restored;
- switching updates root language, title, translated attributes, and checkbox;
- the chosen language is persisted;
- invalid or throwing storage safely falls back to Chinese;
- repeated initialization does not duplicate listeners.

CSS contract tests will verify the inactive-language rule, focus state, slider
layout, mobile behavior, and reduced-motion compatibility. Finally, the complete
Python suite, Python compilation, Node syntax check, and Git diff check must pass.

## Non-Goals

- translating `/kozekilmu`, the downloader, or the user guide;
- changing official LMU names or source material;
- adding a translation framework, external service, new package, or API;
- changing the downloader, queue, extraction, conversion, or network logic;
- refactoring the shared motion system or unrelated page styling.
