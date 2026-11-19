// Per-viewer conveniences (composer options, dismissed failures). Storage can be missing or blocked,
// so every read falls back to a default and every write is optional.
const PREFIX = "gtd.";

export function load(name, fallback) {
  try {
    const raw = window.localStorage.getItem(PREFIX + name);
    return raw == null ? fallback : JSON.parse(raw);
  } catch {
    return fallback;
  }
}

export function save(name, value) {
  try {
    window.localStorage.setItem(PREFIX + name, JSON.stringify(value));
  } catch {
    // Preferences are optional; the app works the same without them.
  }
}
