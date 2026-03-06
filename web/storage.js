const DRAFT_KEY = "abm-web-demo-draft";

export function saveDraft(text) {
  try {
    localStorage.setItem(DRAFT_KEY, String(text || ""));
  } catch (_err) {}
}

export function loadDraft() {
  try {
    return localStorage.getItem(DRAFT_KEY) || "";
  } catch (_err) {
    return "";
  }
}
