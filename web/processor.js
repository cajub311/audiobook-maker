const AVG_CHARS_PER_SECOND = 28;
const MAX_DEMO_CHARS = 7000;
const DEFAULT_MAX_CHARS_PER_CHAPTER = 2600;

function countWords(text) {
  const normalized = String(text || "").trim();
  if (!normalized) {
    return 0;
  }
  return normalized.split(/\s+/).length;
}

function normalizeText(rawText) {
  return String(rawText || "")
    .replace(/\r/g, "")
    .replace(/[ \t]+\n/g, "\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

function estimateSecondsFromChars(chars, rate = 1) {
  const safeRate = Number.isFinite(rate) ? Math.max(0.5, Math.min(2.5, Number(rate))) : 1;
  return Math.max(2, Math.round(chars / (AVG_CHARS_PER_SECOND * safeRate)));
}

function splitVeryLongBlock(block, maxChars) {
  const chunks = [];
  const sentences = String(block || "").match(/[^.!?]+[.!?]+|[^.!?]+$/g) || [String(block || "")];
  let current = "";

  for (const sentenceRaw of sentences) {
    const sentence = sentenceRaw.trim();
    if (!sentence) {
      continue;
    }
    const candidate = current ? `${current} ${sentence}` : sentence;
    if (candidate.length <= maxChars) {
      current = candidate;
      continue;
    }
    if (current) {
      chunks.push(current.trim());
    }
    if (sentence.length <= maxChars) {
      current = sentence;
      continue;
    }
    for (let index = 0; index < sentence.length; index += maxChars) {
      chunks.push(sentence.slice(index, index + maxChars).trim());
    }
    current = "";
  }

  if (current.trim()) {
    chunks.push(current.trim());
  }

  return chunks;
}

function chunkTextByParagraphs(text, maxChars) {
  const source = String(text || "").trim();
  if (!source) {
    return [];
  }
  if (source.length <= maxChars) {
    return [source];
  }

  const paragraphs = source.split(/\n{2,}/).map((part) => part.trim()).filter(Boolean);
  const chunks = [];
  let current = "";

  for (const paragraph of paragraphs) {
    const candidate = current ? `${current}\n\n${paragraph}` : paragraph;
    if (candidate.length <= maxChars) {
      current = candidate;
      continue;
    }
    if (current) {
      chunks.push(current.trim());
      current = "";
    }
    if (paragraph.length <= maxChars) {
      current = paragraph;
      continue;
    }
    for (const longChunk of splitVeryLongBlock(paragraph, maxChars)) {
      chunks.push(longChunk);
    }
  }

  if (current.trim()) {
    chunks.push(current.trim());
  }
  return chunks.filter(Boolean);
}

function splitByHeadings(text) {
  const lines = String(text || "").split("\n");
  const sections = [];
  let activeTitle = "Chapter 1";
  let activeLines = [];
  let untitledCount = 1;

  const flush = () => {
    const body = activeLines.join("\n").trim();
    if (!body) {
      return;
    }
    sections.push({
      title: activeTitle || `Chapter ${sections.length + 1}`,
      text: body,
    });
  };

  for (const lineRaw of lines) {
    const line = lineRaw.trim();
    const headingMatch = line.match(/^(chapter|part)\b(.+)?$/i);
    const markdownHeadingMatch = line.match(/^#{1,3}\s+(.+)$/);

    if (headingMatch || markdownHeadingMatch) {
      flush();
      const headingText = headingMatch
        ? `${headingMatch[1]}${headingMatch[2] || ""}`.trim()
        : markdownHeadingMatch[1].trim();
      activeTitle = headingText || `Chapter ${untitledCount}`;
      activeLines = [];
      untitledCount += 1;
      continue;
    }

    activeLines.push(lineRaw);
  }

  flush();
  return sections;
}

export function formatDuration(totalSeconds) {
  const safeSeconds = Math.max(0, Math.round(Number(totalSeconds) || 0));
  const hours = Math.floor(safeSeconds / 3600);
  const minutes = Math.floor((safeSeconds % 3600) / 60);
  const seconds = safeSeconds % 60;
  if (hours > 0) {
    return `${hours}h ${minutes}m ${seconds}s`;
  }
  return `${minutes}m ${seconds}s`;
}

export function buildAudiobookProject({ title, text, maxCharsPerChapter = DEFAULT_MAX_CHARS_PER_CHAPTER }) {
  const normalizedTitle = String(title || "").trim() || "Untitled Audiobook";
  const normalizedText = normalizeText(text);
  if (!normalizedText) {
    throw new Error("Please provide text before building your audiobook project.");
  }

  const inputSections = splitByHeadings(normalizedText);
  const workingSections = inputSections.length > 0
    ? inputSections
    : [{ title: "Chapter 1", text: normalizedText }];

  const chapters = [];
  const safeMaxChars = Math.max(600, Number(maxCharsPerChapter) || DEFAULT_MAX_CHARS_PER_CHAPTER);

  for (const section of workingSections) {
    const chunks = chunkTextByParagraphs(section.text, safeMaxChars);
    if (chunks.length <= 1) {
      const chapterText = chunks[0] || section.text;
      chapters.push({
        id: `chapter-${chapters.length + 1}`,
        index: chapters.length + 1,
        title: section.title,
        text: chapterText,
        chars: chapterText.length,
        words: countWords(chapterText),
        estimatedSeconds: estimateSecondsFromChars(chapterText.length),
      });
      continue;
    }

    chunks.forEach((chunk, chunkIndex) => {
      chapters.push({
        id: `chapter-${chapters.length + 1}`,
        index: chapters.length + 1,
        title: `${section.title} (${chunkIndex + 1})`,
        text: chunk,
        chars: chunk.length,
        words: countWords(chunk),
        estimatedSeconds: estimateSecondsFromChars(chunk.length),
      });
    });
  }

  const totalChars = chapters.reduce((sum, chapter) => sum + chapter.chars, 0);
  const totalWords = chapters.reduce((sum, chapter) => sum + chapter.words, 0);
  const totalSeconds = chapters.reduce((sum, chapter) => sum + chapter.estimatedSeconds, 0);

  return {
    id: `ab_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`,
    createdAt: new Date().toISOString(),
    title: normalizedTitle,
    fullText: normalizedText,
    totalChars,
    totalWords,
    estimatedSeconds: totalSeconds,
    estimatedDurationLabel: formatDuration(totalSeconds),
    chapters,
  };
}

export function makeDemoProject(rawText) {
  const text = normalizeText(rawText);
  const previewText = text.slice(0, MAX_DEMO_CHARS);
  const project = buildAudiobookProject({
    title: "Demo Audiobook",
    text: previewText,
    maxCharsPerChapter: 1700,
  });

  return {
    previewText: project.fullText,
    summary: {
      demoMode: true,
      originalChars: text.length,
      previewChars: project.totalChars,
      estimatedSeconds: project.estimatedSeconds,
      estimatedMinutes: Math.round((project.estimatedSeconds / 60) * 10) / 10,
      chapterHints: project.chapters.length,
    },
  };
}
