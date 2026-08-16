# User Guide Tilt Reduction Design

## Goal

Reduce the pointer-following tilt on the User Guide to 40% of its current strength without changing the download page or other shared motion behavior.

## Scope

- Add a per-surface tilt-strength attribute supported by the shared motion runtime.
- Set both User Guide motion surfaces—the table of contents and document panel—to `0.4` strength.
- Keep the existing sheen, pointer tracking, transitions, reduced-motion behavior, layout, and page content unchanged.
- Preserve the current default strength for every surface that does not opt in.

## Behavior

The motion runtime reads `data-motion-tilt-strength` as a multiplier from `0` to `1`. Missing or invalid values use the existing full-strength default. User Guide surfaces use `0.4`, so the existing maximum `0.6deg` tilt becomes `0.24deg` while all other pages remain at `0.6deg`.

## Validation

- A runtime test proves default surfaces still reach `0.6deg` and a `0.4` surface reaches `0.24deg`.
- The User Guide template test proves both Guide surfaces opt into `0.4` strength.
- Existing motion and Web Guide tests remain green.
