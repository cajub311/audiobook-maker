const DRAFT_KEY = "abm-web-demo-draft";

export function saveDraft(text) {
  try {
    localStorage.setItem(DRAFT_KEY, String(text || ""));
    return { ok: true };
  } catch (err) {
    return { ok: false, error: err.message };
  }
}

export function loadDraft() {
  try {
    return localStorage.getItem(DRAFT_KEY) || "";
  } catch (err) {
    console.warn("loadDraft failed:", err.message);
    return "";
  }
}
