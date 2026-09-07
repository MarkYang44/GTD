# Refined Petronas frontend

Approved by user: implement the proposed restrained dark design while preserving the Petronas green theme throughout the frontend.

Keep primary #009b95 and accent #00a19b, all branding text, character assets, media images, routes, bilingual controls and download behavior. Use system sans-serif typography for controls and user-guide text. User amendment 2026-09-08: restore original editorial fonts in screenshot-selected homepage hero/metrics/footer, LMU hero introduction and titles, circuit card text/names; retain the signature and rank numeral editorial fonts. Homepage headline uses Cormorant Garamond italic, other restored areas use the original Palatino UI Italic stack. Remove grid/noise and orbital decoration from the visible presentation. Use subdued green atmosphere on a dark neutral background, consistent soft corners, thin borders and restrained navigation translucency.

Compress homepage hero and metrics to bring inputs into view sooner. Keep separate audio/video workflows. Four pages share a final presentation stylesheet instead of adding more divergent page styles.

Use a calm motion profile on all four documents: short opacity/6px entrance for content, no text blur, pointer tilt, tracking sheen or scroll parallax; interactive download workspace is immediately visible. Preserve low-motion access and existing fail-open behavior. Details expansion gets a brief opacity entrance where supported, without concealing native keyboard behavior. Do not add dependencies or change download APIs.

Verify desktop/mobile geometry, green accent and system typography across four pages; input remains stable on hover, reduced motion has no animation, language switching and history still work. Run full unit/Node/browser checks. Local commit only, already authorized.
