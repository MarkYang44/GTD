# LMU V1.4.2 Tracks, Cars, and Sleeper Picks Design

**Date:** 2026-09-22  
**Status:** Approved design, awaiting written-spec review  
**Scope:** `/kozekilmu/tracks`, `/kozekilmu/cars`, and LMU content history

## Goal

Bring the GTD LMU guide up to the V1.4.2 content baseline by adding Michelin Raceway Road Atlanta and the Streets of Long Beach, completing the playable Hypercar and LMGT3 catalog, and adding one separately presented Sleeper Pick for each class at every circuit.

The feature must preserve the existing bilingual, dark/light, Petronas-green interface and the established route, search, favorite, comparison, and content-snapshot behavior.

## Verified release scope

The official 2026-09-22 release identifies V1.4.2 as the current update and adds Road Atlanta and Long Beach through US Track Pack 2. The official announcement describes Road Atlanta as a flowing circuit with blind crests and camber changes, and Long Beach as LMU's first true street circuit with concrete walls, blind entries, and no margin for error.

The official car catalog lists 14 Hypercars and 10 LMGT3 cars. GTD currently has seven Hypercars and nine LMGT3 cars, so this update adds:

- Hypercar: Aston Martin Valkyrie AMR-LMH, Genesis GMR-001, Glickenhaus SCG 007, Isotta Fraschini Tipo 6, Lamborghini SC63, Peugeot 9X8 (original specification), and Vanwall Vandervell 680.
- LMGT3: Mercedes-AMG LMGT3.

Primary release references:

- <https://motorsportgames.com/le-mans-ultimate-releases-version-1-2-update-introducing-paul-ricard-racing-circuit-ginetta-lmp3-race-car-alongside-physics-overhaul-online-competition-refinement-and-team-online-championships-dup/>
- <https://lemansultimate.com/le-mans-ultimate-adds-second-us-track-pack-dlc-alongside-elms-2026-season-liveries/>
- <https://lemansultimate.com/cars/>
- <https://lemansultimate.com/special-events-calendar-q3-4-2026/>

## Data model

Keep the three ordinary recommendations in each `Circuit` class tuple. Add two first-class fields:

- `lmgt3_sleeper: Recommendation`
- `hypercar_sleeper: Recommendation`

Sleeper Picks are deliberately separate from the ordinary top three. A Sleeper Pick may also appear in the same class's ordinary three; overlap is allowed because the two surfaces answer different questions. Every circuit must have exactly one Sleeper Pick per class.

After the update, the catalog contains:

- 18 circuits.
- 24 cars: 14 Hypercars and 10 LMGT3 cars.
- 108 ordinary recommendations: three per class per circuit.
- 36 Sleeper Picks: one per class per circuit.
- 144 displayed recommendation entries in total.

New cars use the existing `Car` structure and receive a local WebP image, official source URL, image-source URL, bilingual strength, and bilingual caution. New circuits use the existing `Circuit` structure and receive a local WebP image, source attribution, length, location, DLC state, bilingual character, challenge, advice, and ordinary recommendations in addition to the two Sleeper fields.

## Recommendation method and evidence boundary

A Sleeper Pick is a car that is not necessarily the obvious popular choice but gives a typical driver a manageable route to competitive pace.

Selection considers four qualities:

1. Stable braking behavior.
2. Predictable traction and balance.
3. A broad operating window or tolerance for the circuit's kerbs, bumps, walls, elevation, or loaded corners.
4. Vehicle traits that match the circuit's layout and therefore offer credible pace potential.

Source priority is:

1. Official LMU release, circuit, and car pages for release facts and first-party descriptions.
2. RaceControl and Coach Dave Academy driving guides for handling observations.
3. Version-specific BoP or leaderboard evidence only when its version and conditions can be verified.

The release-day source set does not provide a uniform V1.4.2 cross-car lap-time test for every circuit. Therefore Sleeper selections are editorial recommendations, not a fastest-car ranking or a claim of driving validation. Their review metadata remains compatibility-unverified unless exact-version evidence exists. The UI must state this boundary in both languages. No numerical pace, setup, or BoP claim may be inferred without a matching source.

When a Sleeper also appears in the ordinary top three, its Sleeper explanation must independently describe why it combines accessibility with pace potential; it must not merely copy the ordinary fit sentence.

## Circuit content

Add `road-atlanta` and `long-beach` to the circuit source map and circuit tuple. Use the official announcement as the circuit source if individual official circuit pages are not yet published. Record the official event characteristics without inventing detailed corner or setup claims.

Add Chinese search aliases for both circuits, including common forms such as `亚特兰大之路`, `罗德亚特兰大`, `长滩`, and `长滩街道赛道`.

Track practice notes must separate the sourced observation from the editorial exercise:

- Road Atlanta: build references progressively over blind crests and compare consistency through flowing elevation changes.
- Long Beach: prioritize repeatable braking and precise placement before reducing wall margin.

## Interface and behavior

Render a compact `Sleeper之选 / Sleeper Pick` card after each class's existing three recommendations. It uses the existing Petronas-green visual language with a distinct badge and border treatment, without introducing an unrelated accent palette.

Sleeper Picks participate in all relevant derived behavior:

- Track-card car metadata used by search and car filtering.
- Reverse circuit recommendations on car cards.
- Car comparison and favorites through the existing car catalog.
- Bilingual switching, including labels, reasons, source status, title text, alt text, and accessibility text.
- Dark and light themes, responsive layout, reduced motion, and no-JavaScript readable fallback.

Existing routes and navigation order do not change.

## Content versioning

Update the guide content date to 2026-09-22 and update the official game reference to V1.4.2 with the official release URL. Existing snapshots are immutable.

Publish a new `2026.09.22.1` snapshot whose bilingual summary accurately lists:

- Two added circuits.
- Eight added cars.
- Ordinary recommendations for the two new circuits.
- One Sleeper Pick per class across all 18 circuits.
- New bilingual source observations and practice exercises.

The publishing command must generate the snapshot and append the manifest; it must not overwrite an older snapshot.

## Validation and failure handling

Tests must fail clearly when:

- The circuit or car counts differ from 18 and 24.
- The class counts differ from 14 Hypercars and 10 LMGT3 cars.
- Any circuit lacks exactly three ordinary recommendations or exactly one Sleeper Pick per class.
- A recommendation references an unknown car or the wrong class.
- A new car or circuit lacks bilingual text, a source, or a local image.
- Sleeper Picks are absent from search metadata or reverse recommendations.
- English mode exposes Chinese UI copy.
- The working content differs from the latest published snapshot.

Overlap between a Sleeper Pick and the same class's ordinary three is valid and must not be rejected.

Verification covers focused Python tests, the full unit suite, JavaScript syntax and language harnesses, snapshot consistency, `git diff --check`, and browser QA at desktop and mobile widths in both themes and languages. Browser QA must check both new tracks, at least one newly added car, one overlapping Sleeper case if present, filter behavior, comparison behavior, and readable source-status text.

## Non-goals

- No LMP2, LMP3, or GTE recommendation expansion.
- No setup files, claimed optimal settings, or unsupported lap-time ranking.
- No route, navigation, downloader, strategy-calculator, account, or persistence changes.
- No redesign outside the compact Sleeper presentation and necessary catalog-count copy.
- No commit or push of downloaded source media outside the intended local WebP guide assets.

