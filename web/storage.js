const DRAFT_KEY = "abm-web-demo-draft";

export function saveDraft(text) {
  try {
    localStorage.setItem(DRAFT_KEY, String(text || ""));
    return { ok: true };
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : String(err) };
  }
}

export function loadDraft() {
  try {
    return localStorage.getItem(DRAFT_KEY) || "";
  } catch (err) {
    console.error("Failed to load demo draft from localStorage:", err);
    return null;
  }
}
