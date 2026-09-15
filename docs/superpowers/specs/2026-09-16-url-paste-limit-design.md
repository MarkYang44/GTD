# URL Paste Limit Design

## Goal

Prevent users from pasting more than 20 non-empty URL lines into either the
video or audio input, and notify them when the input reaches the limit.

## Interaction

- Apply the same behavior to `#videoUrls` and `#audioUrls`.
- Before inserting clipboard text, calculate the textarea's resulting value,
  including any currently selected text that the paste would replace.
- Count trimmed, non-empty lines in that resulting value.
- If the result contains fewer than 20 lines, allow the paste normally.
- If the result contains exactly 20 lines, allow the paste and show a localized
  message that the 20-line limit has been reached and no more links should be
  pasted.
- If the result contains more than 20 lines, cancel the entire paste, keep the
  textarea unchanged, and show the same localized message.
- Do not truncate clipboard text or silently discard individual lines.

## Scope

This is a paste-time frontend guard only. It does not change playlist selection
limits, backend validation, download concurrency, typing behavior, or public
APIs. No CSS or template changes are required.

## Verification

Add a Node-based frontend test covering both textareas, normal pasting, reaching
20 lines, rejecting a paste that would exceed 20 lines, and selection
replacement. Run the focused test, the existing frontend language harness,
JavaScript syntax checking, the full Python suite, and `git diff --check`.
