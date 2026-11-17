// Only this opaque reference lives in tab storage. Dataset rows, filters, tokens and AI text stay out of it.
const KEY = "business-insights-workspace-v1";

export function readWorkspaceReference(storage) {
  try {
    storage ??= globalThis.sessionStorage;
    const value = storage.getItem(KEY);
    return /^[A-Za-z0-9_-]{32}$/.test(value || "") ? value : null;
  } catch { return null; }
}

export function writeWorkspaceReference(id, storage) {
  try {
    storage ??= globalThis.sessionStorage;
    if (/^[A-Za-z0-9_-]{32}$/.test(id || "")) storage.setItem(KEY, id);
  } catch { /* Blocked tab storage leaves the current dashboard usable. */ }
}

export function clearWorkspaceReference(storage) {
  try { (storage ?? globalThis.sessionStorage).removeItem(KEY); } catch { /* Private-browser storage may be unavailable. */ }
}
