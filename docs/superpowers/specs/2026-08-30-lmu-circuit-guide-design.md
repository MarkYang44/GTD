# LMU Circuit Guide Design

**Date:** 2026-08-30  
**Project:** GTD — Generalized Transmedia Downloader

## Goal

Extend the existing Kozeki Ui LMU easter egg with a separate circuit guide page.
The guide covers every circuit currently listed on the official Le Mans Ultimate
website, including DLC, and gives ordinary players three LMGT3 and three
Hypercar recommendations for each circuit.

The feature is presentation-only. It must not alter downloader, queue,
conversion, API, or service behavior.

## Scope

- Add a new page at `/kozekilmu/tracks`.
- Keep `/kozekilmu` as the existing victory archive.
- Add matching navigation to both pages:
  - `VICTORY ARCHIVE / 冠军档案`
  - `CIRCUIT GUIDE / 赛道指南`
- Cover all 16 circuits listed by LMU on 2026-08-30:
  - Bahrain
  - Circuit de Barcelona-Catalunya
  - Circuit de la Sarthe
  - Circuit Paul Ricard
  - Circuit of the Americas
  - Daytona International Speedway
  - Fuji Speedway
  - Imola
  - Interlagos
  - Lusail International Circuit
  - Monza
  - Portimão
  - Sebring International Raceway
  - Silverstone International
  - Spa-Francorchamps
  - WeatherTech Raceway Laguna Seca
- Mark official DLC circuits with a visible `DLC` badge.
- Give every circuit exactly three LMGT3 and three Hypercar recommendations.
- Exclude LMP2, LMP3, and GTE recommendations.

## Source Policy

Primary sources are:

- [LMU circuits](https://lemansultimate.com/circuits/)
- [LMU cars](https://lemansultimate.com/cars/)
- Individual LMU circuit and car pages
- FIA WEC and manufacturer pages only when the LMU page lacks a factual detail

Track and car images should come from official LMU media URLs. They will be
downloaded, resized, and encoded as local WebP assets so the page remains stable
and works offline. Each source URL will be recorded in a project-local source
manifest and summarized in the page attribution area.

If an official image cannot be obtained, the card uses a themed gradient
placeholder. The implementation must not silently substitute an unverified
third-party image.

## Content Model

Circuit content lives outside the template in one focused Python or JSON data
module. Each circuit record contains:

- stable slug and display name;
- country or region;
- official length where verified;
- circuit character and key challenges;
- concise driving advice;
- DLC status;
- local image path and official source URL;
- exactly three LMGT3 recommendations;
- exactly three Hypercar recommendations.

Each car recommendation contains the car name, local image path, a short reason,
its main advantage, and one caution. Recommendations target ordinary players,
prioritizing stability, braking confidence, tyre management, traffic handling,
and suitability to the circuit rather than claiming an absolute fastest car.

The page states that recommendations reflect the current public game content and
may change after physics or Balance of Performance updates. Unsupported precise
performance figures must not be invented.

## Page Structure

The guide reuses the existing dark navy, Petronas-green, Cormorant/Palatino,
and shared motion language.

1. Shared top bar and two-page easter-egg navigation.
2. Spacious hero introducing the circuit guide and its update basis.
3. Responsive circuit-card grid:
   - two columns on wide screens;
   - one column on mobile;
   - wide official circuit image;
   - location, length, character, and DLC metadata;
   - a concise introduction visible before expansion.
4. Native `<details>` expansion for each circuit:
   - key challenges and driving advice;
   - separate LMGT3 and Hypercar recommendation groups;
   - three vehicle cards per group.
5. Source attribution, version caveat, and link back to the victory archive.

Using native `<details>` keeps the page readable without JavaScript and avoids
rendering 96 recommendation cards as permanently expanded dense content.

## Motion and Accessibility

- Reuse the existing shared motion runtime; add no frontend dependency.
- Limit motion to restrained reveal, subtle parallax, and surface sheen.
- Preserve static readability when JavaScript is unavailable.
- Respect `prefers-reduced-motion`.
- Use semantic headings, native interactive controls, visible focus styles, and
  descriptive image alt text.
- Lazy-load below-the-fold images and provide explicit dimensions to reduce
  layout shift.
- Do not hide essential content behind hover-only interaction.

## Failure Handling

- Missing local images render a styled placeholder without breaking the page.
- Malformed optional metadata is omitted rather than displayed as fake values.
- Source links open safely with `rel="noopener noreferrer"`.
- The route remains read-only and performs no live third-party fetches.

## Testing and Validation

Automated tests will verify:

- `/kozekilmu/tracks` returns successfully;
- both easter-egg pages expose the two-page navigation;
- all 16 circuit records render once;
- every circuit has exactly three LMGT3 and three Hypercar recommendations;
- DLC labels match the official index snapshot;
- all referenced local images exist and are valid WebP files;
- official source links and attribution are present;
- semantic `<details>`, responsive CSS, lazy loading, focus handling, and reduced
  motion fallbacks are retained;
- the original `/kozekilmu` content and existing tests remain unchanged.

Final validation includes the full Python test suite, compile and diff checks,
plus visual QA at desktop and mobile widths. The service used for visual QA is
stopped afterward.

## Non-Goals

- No live race telemetry, setup calculator, lap-time ranking, or user accounts.
- No claim that recommendations are objectively fastest.
- No modification to download, extraction, conversion, task, or API logic.
- No redesign of the original victory archive beyond the shared navigation.
