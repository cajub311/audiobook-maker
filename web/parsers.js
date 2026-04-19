// Streaming file parsers for the audiobook maker.
// Supports plain text (.txt/.md), EPUB, DOCX, and PDF.
// EPUB and DOCX use fflate (jsDelivr CDN) for ZIP extraction.
// PDF uses pdfjs-dist (jsDelivr CDN).
// All parsers report live progress through the onProgress callback.

const FFLATE_URL = "https://cdn.jsdelivr.net/npm/fflate@0.8.2/esm/browser.js";
const PDFJS_URL = "https://cdn.jsdelivr.net/npm/pdfjs-dist@4.10.38/build/pdf.min.mjs";
const PDFJS_WORKER_URL = "https://cdn.jsdelivr.net/npm/pdfjs-dist@4.10.38/build/pdf.worker.min.mjs";

let fflatePromise = null;
let pdfjsPromise = null;

function loadFflate() {
  if (!fflatePromise) {
    fflatePromise = import(/* @vite-ignore */ FFLATE_URL).then((mod) => {
      // Handle both named-export ESM and default-wrapped CJS-compat bundles
      if (mod && typeof mod.unzipSync === "function") return mod;
      if (mod && mod.default && typeof mod.default.unzipSync === "function") return mod.default;
      throw new Error("fflate loaded but unzipSync not found — unexpected module format");
    });
  }
  return fflatePromise;
}

function loadPdfjs() {
  if (!pdfjsPromise) {
    pdfjsPromise = import(/* @vite-ignore */ PDFJS_URL).then((mod) => {
      const api = mod && (mod.GlobalWorkerOptions ? mod : mod.default);
      if (!api) throw new Error("PDF.js loaded but API not found — unexpected module format");
      try {
        api.GlobalWorkerOptions.workerSrc = PDFJS_WORKER_URL;
      } catch (_err) {
        // worker setup is best-effort; pdfjs will fall back to main-thread parsing
      }
      return api;
    });
  }
  return pdfjsPromise;
}

async function readFileWithProgress(file, onProgress) {
  if (!file.stream) {
    const buffer = await file.arrayBuffer();
    onProgress && onProgress(1, `Read ${Math.round(buffer.byteLength / 1024)} KB`);
    return new Uint8Array(buffer);
  }
  const reader = file.stream().getReader();
  const chunks = [];
  let received = 0;
  const total = file.size || 0;
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    chunks.push(value);
    received += value.byteLength;
    if (onProgress) {
      const pct = total ? received / total : Math.min(0.95, 0.02 + received / 524288);
      onProgress(
        pct,
        `Read ${Math.round(received / 1024)} KB${total ? ` / ${Math.round(total / 1024)} KB` : ""}`,
      );
    }
  }
  const out = new Uint8Array(received);
  let offset = 0;
  for (const chunk of chunks) {
    out.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return out;
}

function stripExt(name) {
  return (name || "").replace(/\.[^.]+$/, "");
}

function stripHtmlToText(html) {
  const doc = new DOMParser().parseFromString(html, "text/html");
  doc.querySelectorAll("script, style, nav, header, footer").forEach((n) => n.remove());
  const blockTags = new Set(
    ["P", "DIV", "LI", "H1", "H2", "H3", "H4", "H5", "H6", "BLOCKQUOTE", "PRE", "TR"],
  );
  let text = "";
  const walk = (node) => {
    if (!node) return;
    if (node.nodeType === 3) {
      text += node.nodeValue;
      return;
    }
    if (node.nodeType !== 1) return;
    if (node.tagName === "BR") {
      text += "\n";
      return;
    }
    const block = blockTags.has(node.tagName);
    for (const child of node.childNodes) walk(child);
    if (block) text += "\n\n";
  };
  walk(doc.body || doc.documentElement);
  return text.replace(/[ \t]+/g, " ").replace(/\n{3,}/g, "\n\n").trim();
}

// Case-insensitive key lookup in a ZIP entry map
function zipKey(map, path) {
  const low = path.toLowerCase();
  return Object.keys(map).find((k) => k.toLowerCase() === low) || null;
}

async function parseTxt(file, onProgress) {
  const bytes = await readFileWithProgress(file, (p, n) => onProgress && onProgress(p * 0.9, n));
  const text = new TextDecoder("utf-8", { fatal: false }).decode(bytes);
  onProgress && onProgress(1, `Loaded ${Math.round(text.length / 1000)} KB`);
  return { text, title: stripExt(file.name), author: "", kind: "txt" };
}

function normalizeKey(map, key) {
  const low = key.toLowerCase();
  return Object.keys(map).find((k) => k.toLowerCase() === low) || key;
}

async function parseEpub(file, onProgress) {
  onProgress && onProgress(0.05, "Reading EPUB…");
  const bytes = await readFileWithProgress(file, (p) =>
    onProgress && onProgress(0.05 + p * 0.35, "Reading EPUB…"),
  );

  let unzipSync, strFromU8;
  try {
    ({ unzipSync, strFromU8 } = await loadFflate());
  } catch (err) {
    throw new Error(`Could not load EPUB parser library: ${err.message}. Check your internet connection.`);
  }

  onProgress && onProgress(0.45, "Unpacking EPUB…");
  let unzipped;
  try {
    unzipped = unzipSync(bytes, { filter: (f) => !f.name.endsWith("/") });
  } catch (err) {
    throw new Error(`Could not unpack EPUB — the file may be corrupted or password-protected: ${err.message}`);
  }

  // Case-insensitive container.xml lookup (EPUB spec allows any casing)
  const containerKey = zipKey(unzipped, "META-INF/container.xml");
  let opfPath = null;
  if (containerKey) {
    try {
      const xml = new DOMParser().parseFromString(strFromU8(unzipped[containerKey]), "application/xml");
      const rootfile = xml.querySelector("rootfile");
      if (rootfile) opfPath = rootfile.getAttribute("full-path");
    } catch (_err) {
      // container.xml parse failure — try falling back to file scan
    }
  }

  let title = stripExt(file.name);
  let author = "";
  let spineFiles = [];

  if (opfPath) {
    const opfKey = zipKey(unzipped, opfPath) || opfPath;
    if (unzipped[opfKey]) {
      try {
        const opfXml = new DOMParser().parseFromString(strFromU8(unzipped[opfKey]), "application/xml");
        title = opfXml.querySelector("metadata title")?.textContent?.trim() || title;
        author = opfXml.querySelector("metadata creator")?.textContent?.trim() || "";
        const manifest = {};
        opfXml.querySelectorAll("manifest > item").forEach((el) => {
          manifest[el.getAttribute("id")] = el.getAttribute("href");
        });
        const base = opfPath.includes("/") ? opfPath.slice(0, opfPath.lastIndexOf("/") + 1) : "";
        opfXml.querySelectorAll("spine > itemref").forEach((el) => {
          const href = manifest[el.getAttribute("idref")];
          if (href) spineFiles.push(decodeURIComponent(base + href));
        });
      } catch (_err) {
        // OPF parse failure — fall back to file scan below
      }
    }
  }

  if (!spineFiles.length) {
    spineFiles = Object.keys(unzipped).filter((k) => /\.(x?html|htm)$/i.test(k)).sort();
  }
  if (!spineFiles.length) {
    throw new Error("No readable content found in this EPUB. It may use an unsupported DRM scheme.");
  }

  const parts = [];
  for (let i = 0; i < spineFiles.length; i++) {
    const key = zipKey(unzipped, spineFiles[i]) || normalizeKey(unzipped, spineFiles[i]);
    const data = unzipped[key];
    if (!data) continue;
    try {
      const html = strFromU8(data);
      const text = stripHtmlToText(html);
      if (text.trim()) parts.push(text);
    } catch (_err) {
      // skip broken section, keep going
    }
    onProgress && onProgress(
      0.55 + (i / Math.max(1, spineFiles.length)) * 0.4,
      `Section ${i + 1}/${spineFiles.length}`,
    );
  }

  const text = parts.join("\n\n").trim();
  if (!text) throw new Error("EPUB parsed but contained no readable text.");
  onProgress && onProgress(1, `Loaded ${Math.round(text.length / 1000)} KB`);
  return { text, title, author, kind: "epub" };
}

async function parseDocx(file, onProgress) {
  onProgress && onProgress(0.05, "Reading DOCX…");
  const bytes = await readFileWithProgress(file, (p) =>
    onProgress && onProgress(0.05 + p * 0.45, "Reading DOCX…"),
  );

  let unzipSync, strFromU8;
  try {
    ({ unzipSync, strFromU8 } = await loadFflate());
  } catch (err) {
    throw new Error(`Could not load DOCX parser library: ${err.message}. Check your internet connection.`);
  }

  onProgress && onProgress(0.55, "Unpacking DOCX…");
  let unzipped;
  try {
    unzipped = unzipSync(bytes);
  } catch (err) {
    throw new Error(`Could not unpack DOCX — the file may be corrupted or password-protected: ${err.message}`);
  }

  const docKey = zipKey(unzipped, "word/document.xml");
  if (!docKey) {
    throw new Error("No word/document.xml found — this may not be a valid DOCX file.");
  }

  onProgress && onProgress(0.7, "Parsing document…");
  const xml = strFromU8(unzipped[docKey]);
  const doc = new DOMParser().parseFromString(xml, "application/xml");

  // Each <w:p> is a paragraph; collect runs <w:t> within it
  const paragraphs = doc.querySelectorAll("p");
  const parts = [];
  for (const para of paragraphs) {
    const runs = Array.from(para.querySelectorAll("t")).map((t) => t.textContent).join("");
    if (runs.trim()) parts.push(runs.trim());
  }

  let title = stripExt(file.name);
  let author = "";
  const coreKey = zipKey(unzipped, "docProps/core.xml");
  if (coreKey) {
    try {
      const coreXml = new DOMParser().parseFromString(strFromU8(unzipped[coreKey]), "application/xml");
      const t = coreXml.querySelector("title")?.textContent?.trim();
      const a = coreXml.querySelector("creator")?.textContent?.trim();
      if (t) title = t;
      if (a) author = a;
    } catch (_err) {
      // metadata is best-effort
    }
  }

  const text = parts.join("\n\n").trim();
  if (!text) throw new Error("DOCX parsed but contained no readable text.");
  onProgress && onProgress(1, `Loaded ${Math.round(text.length / 1000)} KB`);
  return { text, title, author, kind: "docx" };
}

async function parsePdf(file, onProgress) {
  onProgress && onProgress(0.05, "Reading PDF…");
  const bytes = await readFileWithProgress(file, (p) =>
    onProgress && onProgress(0.05 + p * 0.25, "Reading PDF…"),
  );

  let pdfjs;
  try {
    pdfjs = await loadPdfjs();
  } catch (err) {
    throw new Error(`Could not load PDF parser library: ${err.message}. Check your internet connection.`);
  }

  onProgress && onProgress(0.35, "Parsing PDF…");
  let doc;
  try {
    doc = await pdfjs.getDocument({ data: bytes }).promise;
  } catch (err) {
    throw new Error(`Could not open PDF — it may be password-protected or corrupted: ${err.message}`);
  }

  const pageCount = doc.numPages;
  const parts = [];
  let title = stripExt(file.name);
  let author = "";
  try {
    const meta = await doc.getMetadata();
    if (meta && meta.info) {
      if (meta.info.Title) title = String(meta.info.Title).trim() || title;
      if (meta.info.Author) author = String(meta.info.Author).trim() || "";
    }
  } catch (_err) {
    // metadata is best-effort
  }

  for (let p = 1; p <= pageCount; p++) {
    try {
      const page = await doc.getPage(p);
      const content = await page.getTextContent();
      let pageText = "";
      for (const item of content.items) {
        const s = String(item.str || "");
        pageText += s;
        pageText += item.hasEOL ? "\n" : " ";
      }
      parts.push(pageText.trim());
    } catch (_err) {
      // skip unreadable page
    }
    if (p % 2 === 0 || p === pageCount) {
      onProgress && onProgress(0.35 + (p / pageCount) * 0.6, `Page ${p}/${pageCount}`);
    }
  }

  try {
    await doc.cleanup();
    doc.destroy();
  } catch (_err) {
    // ignore teardown issues
  }

  const text = parts.join("\n\n").trim();
  if (!text) throw new Error("PDF parsed but contained no readable text. It may be a scanned image PDF.");
  onProgress && onProgress(1, `Loaded ${pageCount} pages`);
  return { text, title, author, kind: "pdf" };
}

export async function parseAnyFile(file, onProgress) {
  const name = (file.name || "").toLowerCase();
  const type = (file.type || "").toLowerCase();

  if (name.endsWith(".epub") || type.includes("epub")) return parseEpub(file, onProgress);
  if (name.endsWith(".pdf") || type.includes("pdf")) return parsePdf(file, onProgress);
  if (
    name.endsWith(".docx") ||
    type.includes("wordprocessingml") ||
    type.includes("msword") ||
    type.includes("officedocument")
  ) return parseDocx(file, onProgress);
  if (name.endsWith(".txt") || name.endsWith(".md") || name.endsWith(".rtf") || type.startsWith("text/")) {
    return parseTxt(file, onProgress);
  }
  // Formats we know we can't handle — give a clear message instead of garbled output
  const ext = name.includes(".") ? name.split(".").pop().toUpperCase() : null;
  if (ext && ["DOC", "MOBI", "AZW", "AZW3", "LIT", "CBZ", "CBR"].includes(ext)) {
    throw new Error(
      `${ext} format is not supported. Please convert to EPUB, PDF, DOCX, or TXT first. ` +
      `Calibre (free) can convert most book formats.`,
    );
  }
  // Unknown extension — try as plain text
  return parseTxt(file, onProgress);
}
