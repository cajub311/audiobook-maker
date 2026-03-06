const MAX_DEMO_CHARS = 7000;

export function makeDemoProject(rawText) {
  const text = String(rawText || "").replace(/\s+/g, " ").trim();
  const previewText = text.slice(0, MAX_DEMO_CHARS);
  const estimatedSeconds = Math.max(5, Math.round(previewText.length / 28));
  const chapters = previewText.split(/\b(?:chapter|part)\b/i).filter(Boolean);

  return {
    previewText,
    summary: {
      demoMode: true,
      originalChars: text.length,
      previewChars: previewText.length,
      estimatedSeconds,
      estimatedMinutes: Math.round((estimatedSeconds / 60) * 10) / 10,
      chapterHints: Math.max(1, chapters.length),
    },
  };
}
