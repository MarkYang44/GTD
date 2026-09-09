# LMU sourced practice notes and content revisions

- Add source-attributed bilingual notes for all 16 circuits and 16 cars. Circuit exercises are editorial inferences from official circuit descriptions; car notes summarize individually read Coach Dave LMU driving guides. Separate source observations from suggested exercises. Do not reproduce numerical setups or current pace rankings from historical guides.
- Add per-record game applicability (unverified unless proven), source review date, and source URLs. Reference the checked official V1.4.1.4 release notes without claiming a driving test on that build. Existing circuit/car pairing recommendations remain editorial, not source-endorsed rankings.
- Capture a truthful import baseline and a new content release in versioned JSON snapshots. Add a local publishing/check CLI and a bilingual updates page showing actual before/after changes, with stable links to affected records. Test that edited content requires a new snapshot.
- Render practice and metadata in guide/catalog/comparison, preserve language/theme/accessibility and no-JS reading. Validate all-record coverage, source references, history diffs, regression and browser behavior. Update bilingual docs and commit locally.

## Completion evidence

- Read all 16 official circuit descriptions and all 16 individual Coach Dave LMU car guides. Paraphrased brief observations and clearly separated editorial exercises; kept per-entity source links. Official V1.4.1.4 notes were checked as a build reference, not a driving compatibility test.
- Added 96 pairing review records, 32 practice records, and one build reference. Imported an unverified baseline and published content release 2026.09.09.1; change history compares 129 records with actual before/after fields.
- Shared guide/catalog/comparison presentation retains notes and metadata. Nested disclosure styling and old disclosure test selectors were scoped to the correct controls.
- 437 unit/Node tests passed (2 platform skips); the full browser suite passed 25 tests. After the final metadata wording/date adjustments, all 437 tests and the 3 focused content browser tests passed again. Snapshot check and git diff whitespace check passed. Native Chrome visual review confirmed light-theme history and expanded before/after fields.
- Bilingual README/web guide and the source-maintenance/publishing workflow are documented. No runtime external fetching, new dependencies, or claimed driving tests.
