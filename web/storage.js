const DRAFT_KEY = "abm-web-demo-draft";
const PROJECT_KEY = "abm-audiobook-project";
const PREFS_KEY = "abm-audiobook-preferences";

function safeJsonParse(raw, fallback) {
  if (!raw) {
    return fallback;
  }
  try {
    return JSON.parse(raw);
  } catch (_err) {
    return fallback;
  }
}

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

export function saveProject(project) {
  try {
    if (!project || typeof project !== "object") {
      return { ok: false, error: "Invalid project payload." };
    }
    localStorage.setItem(PROJECT_KEY, JSON.stringify(project));
    return { ok: true };
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : String(err) };
  }
}

export function loadProject() {
  try {
    return safeJsonParse(localStorage.getItem(PROJECT_KEY), null);
  } catch (err) {
    console.error("Failed to load audiobook project from localStorage:", err);
    return null;
  }
}

export function clearProject() {
  try {
    localStorage.removeItem(PROJECT_KEY);
    return { ok: true };
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : String(err) };
  }
}

export function savePreferences(preferences) {
  try {
    const payload = preferences && typeof preferences === "object" ? preferences : {};
    localStorage.setItem(PREFS_KEY, JSON.stringify(payload));
    return { ok: true };
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : String(err) };
  }
}

export function loadPreferences() {
  try {
    return safeJsonParse(localStorage.getItem(PREFS_KEY), {});
  } catch (err) {
    console.error("Failed to load launcher preferences from localStorage:", err);
    return {};
  }
}
