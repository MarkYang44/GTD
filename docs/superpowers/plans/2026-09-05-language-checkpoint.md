# Language implementation checkpoint

User approved implementation and requested local checkpoint commits to protect progress if usage runs out.

Implemented so far: shared language runtime/toggle, preference compatibility, static homepage, bilingual guide/archive, English README and web guide, dynamic homepage localization draft.

Not yet complete: integrate and run dynamic harness; fix inactive-language CSS specificity (format-option span and footer rules override generic hiding); update old tests that asserted exact single-language markup or asset lists; verify all four pages in Safari. Last full test run (during edits) had 393 tests, 5 failures, 2 skips; those results are not final. Shared language and secondary-page tests passed independently.

Temporary verification server runs at 127.0.0.1:8234 via a Codex exec session; existing user server at 8233 was preserved. A new Safari tab is open at the temporary homepage. Stop only the temporary server when done.

Next steps: finish the checklist in 2026-09-05-global-language.md, run complete tests and JS harnesses, browser QA and final local commit. Do not push.
