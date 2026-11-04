# Concurrent batches on the download page

Requested 2026-11-04, as a follow-up to the calm workspace refresh, which listed this as a non-goal. The request was to let people paste and submit new links while earlier batches are still running, without losing track of the running ones. The layout was left to the builder, and the decisions below were made on that basis.

## Intent

`TaskManager` already runs batches side by side on 3 shared worker slots. The page did not: from the first click until the batch finished, `isDownloading` and `setControlsDisabled(true)` disabled both cards and the history picker. Someone with a long playlist downloading had to wait for it before pasting the next link. The lock was a frontend limitation, not something the server needed.

## Goals

- Both cards stay usable while batches download. A card is disabled only while its own links are being parsed, are waiting for an item choice, or are being submitted (seconds). The server accepting the batch releases the card and clears its box.
- A second submission never hides or stops tracking an earlier batch that is still running.
- The live metrics (`#metric-active`, `#metric-queue`) count every batch shown in the panel. Skeleton rows for a batch still being submitted count as queued.
- Task history stays usable at any time and does not interrupt running batches.
- Polling keeps its tested rules: one request in flight, 800 ms when visible and 3 s when hidden, an immediate poll when the page becomes visible, backoff through `window.GtdTaskApi`.

## Non-goals

- Download API changes. Every batch keeps using `GET /api/batch/<id>`, and history keeps using `GET /api/batches`.
- Restoring running batches after a reload. Opening the page still shows the empty state, and history is still the way back.
- Counting work that other tabs or the extraction page started without this page.

## Panel model (my call)

The task panel is a stack of **batch groups**, newest first:

- every batch the page is still tracking because it has not finished, and
- the **focused** batch: the latest submission or history selection.

When the focus changes, finished batches that are not focused leave the panel. They stay in Task history. This matches the old rule that a new batch replaces the finished view, but nothing still running ever leaves. A batch that comes back as 404/410 leaves with an inline task notice ("missing or expired… downloaded files are kept"); the others keep polling.

Rendering:

- **One group** looks like today: the panel heading is the batch title ("Video downloads", "MP3 V0 audio downloads") and the summary is its counts.
- **Two or more groups**: the heading becomes "Download tasks" with "{n} batches · {running} in progress · {finished} finished", and each group gets a compact header: title, creation time, and that batch's counts.
- Each group renders into its own element and is rewritten only when its own data changes, so text selection and open attempt histories in one batch survive updates in another.
- A submission shows skeleton rows in a new group at the top while `POST /api/download` is in flight. The group becomes the real batch once the server accepts it and disappears if the server rejects it.

## Submitting while others run (my call)

- Settings are captured when Download is clicked. The card stays disabled until the server answers, so what a person sees is what gets submitted.
- There is one item-selection panel. While it waits for a choice, the other card can still submit single items. If the other card also needs a choice, it shows an inline notice to finish or cancel the open selection first, and its links stay in the box. The notice clears once that selection is submitted or cancelled.
- A failed direct submission (a single item that needs no choice) is reported in that card's notice, with the links still in the box. A failed submission from the selection panel keeps the panel open with its notice, as before.
- The panel heading shows "Parsing input" or "Choose items to download" only while the panel is otherwise empty. Once batches are listed, it describes them.

## Polling

One serial loop sweeps every batch that still needs updates, one request at a time, then waits for the interval. A network or server error ends the sweep early, shows "Connection unavailable. Retrying automatically…", and backs off. Answers for batches that have left the panel, or that changed because of a task action while the request was in flight, are ignored. Task actions and history selection mark their batch for refresh and start the loop. The loop stops once every batch shown has finished.

## Task actions and history

- Cancel, retry and redownload include the batch ID of their row. **Retry all failed tasks** retries the failed tasks in every batch shown.
- Selecting a saved batch focuses it: the batch moves to the top of the panel or is added there, then refreshes. Running batches stay below it.
- The history list refreshes after each accepted submission and whenever a batch finishes, so the picker can show the focused batch and its counts stay current.

## Verification

Node harnesses run the real `index.js` against a fake DOM: concurrent submissions, sweeps across batches, metrics, history focus, missing batches, late answers, backoff, and per-card locking. Unit tests cover the source-level guarantees. The Chrome browser tests submit a second batch while the first is running and check that both stay visible and are counted.
