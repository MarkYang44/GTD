# LMU weekly calendar — approved scope

The user approved the feasibility review with automatic updating removed. Implement in the current GTD checkout without committing, pushing, changing services, or adding scheduled jobs.

- Flask/Jinja page `/kozekilmu/calendar`, shared navigation, language/theme, native details, responsive overview and event cards.
- Local JSON in `data/lmu/calendar/`, versioned schema, explicit UTC-offset session timestamps displayed in Europe/London. Events and sessions are separate; official event tier and eligibility are separate.
- Unknown official values are null, rendered Not Published. Initial calendar is empty; no invented current races. Recommendations reference existing car IDs, with at most three per class and eligibility/evidence labels. Unsupported classes remain readable without invented recommendations.
- Strategies per car reuse existing JavaScript pure calculator. All seven inputs are explicit (no silent defaults); calculations are Estimated and retain bilingual calculation notes. Official mandatory-stop rules are separate from computed refueling stops. Tires and traffic are editorial notes with unknown states.
- Manual Python CLI validates candidate JSON, serializes through a single writer lock, atomically archives/replaces, preserves previous valid data and records failure state. Repeated identical import is a no-op. Reading fallback never replaces files. New-week imports never reuse stale unknown fields silently.
- Offline/source unavailability does not block local server rendering. Browser network status is explanatory only; no external request is needed. No AJAX loading spinner because data is server-rendered.
- No fetching, cron, workflow, secrets, npm pipeline or framework. Windows receives tzdata for ZoneInfo.
- Test validation, timezone transitions, immutable week archives, failure recovery, routes, JS estimates, responsive bilingual/theme/no-JS rendering; run existing regression suite.
