# Calm workspace refresh

Requested 2026-11-04: review the Web frontend for remaining chances to make it more concise, elegant and humane, then implement the plan without a question round.

## Intent

Keep the approved Refined Petronas identity and remove what still gets between a person and the core loop: paste links, choose output, watch progress, find the file. Every helper sentence, label and control must earn its place; feedback appears next to the thing it describes and never blocks the page.

## Keep

- Palette tokens (`--primary #009b95`, `--accent #00a19b`, dark neutral-green surfaces, light theme), Cormorant Garamond italic headline, Palatino UI Italic editorial accents (hero kicker and description, metrics, footer), system UI type for controls.
- Brand and signature copy, character easter-egg links, footer disclaimer, `YOUTUBE + INSTAGRAM + BILIBILI` kicker.
- Separate video and audio workflows, calm motion profile, bilingual and theme switches, every route, API, element ID and inline handler.

## Changes

1. **Structure.** Remove the numbered eyebrow labels (`01 / DOWNLOAD`, `02 / AUDIO`, `02 / OPERATIONS`, `03 / 使用说明`…); their numbering collided and stayed English in Chinese mode. Drop the "Choose your output" header; the two cards carry `h2` titles. The local-extraction entry moves from the hero into the audio card description, where it is relevant. Live metrics (active, queued, parallel limit) move from the hero into the task panel header with bilingual labels, and the page scrolls to the task panel when a batch starts.
2. **Copy.** Shorter card descriptions and subtitle note. The download location placeholder names the real default folder, so the always-on hint line disappears; hints appear only when they add something (no folder picker here). Static "N saved batches" feedback and the 32-character batch ID leave the task summary. While a collection waits for a choice, the panel says so instead of "Parsing input".
3. **Controls.** Subtitle options become checkbox chips with a visible check, distinct from the single-choice audio-format control. Format controls size to their content (fixes the empty box on the extraction page). The turbo row names Bilibili, and its switch gets an accessible name. Text is at least 12 px (badges 11 px). The theme switch uses moon/sun icons instead of two words, freeing header space on phones.
4. **Feedback.** Blocking `alert()` dialogs are replaced by inline notices in the card, preview or task panel that re-translate on language switch. A live `n / 20 lines` counter makes the paste limit visible before it is hit. Ctrl/⌘ + Enter in a link box starts that download.
5. **Tasks.** Title first (generated `第 N 项` placeholders localize to `Item N`), URL second; a progress bar from the reported percentage; attempt history only after a retry; the saved path selects in one click.
6. **Stylesheets.** `index.css` becomes the single stylesheet for the download and extraction pages (tokens, components, responsive rules). Those pages stop loading `refined.css`, whose download-only overrides are deleted. Dead decoration (grid/noise layers, hidden orbit, card stripe, legacy spacer) is removed. Field and warning colors become tokens, so the light theme follows without per-component overrides.
7. **Guide.** Drop the numbered kicker and the duplicate "User guide" label inside the document; the contents column and the document no longer sit on a second, navy-tinted frame.

## Non-goals

- Submitting new links while a batch runs. The page polls one batch at a time; changing that model is a separate piece of work.
- LMU easter-egg pages beyond the shared theme switch, download APIs, dependencies.

## Verification

Unit tests and Node harnesses; browser tests against Chrome; screenshots of the download, extraction and guide pages on desktop and phone widths in both themes and languages; README screenshots regenerated from an isolated session.
