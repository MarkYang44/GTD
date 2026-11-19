// Inline notices for problems that belong to a place; transient success goes to toasts instead.
import { errorParts } from "./strings.js";
import { $, fillCallout } from "./ui.js";
import { state, t } from "./store.js";

export function notice(id, message, tone = "error") {
  const target = $(`${id}-notice`);
  if (!target) return;
  if (!message) {
    target.hidden = true;
    target.replaceChildren();
    return;
  }
  const parts = typeof message === "string" ? { message } : message;
  fillCallout(target, { tone, codeLabel: t("errorCode"), ...parts });
  target.hidden = false;
}

export function showError(id, error) {
  notice(id, errorParts(error, state.language));
}
