// Streaming file parsers for the audiobook maker.
// Supports plain text (.txt/.md), EPUB (via fflate from jsDelivr), and
// PDF (via pdfjs-dist from jsDelivr). All three report live progress
// through the supplied onProgress callback so large uploads never feel
// like they are stuck.

const FFLATE_URL = "https://cdn.jsdelivr.net/npm/fflate@0.8.2/esm/browser.js";
const PDFJS_URL = "https://cdn.jsdelivr.net/npm/pdfjs-dist@4.10.38/build/pdf.min.mjs";
const PDFJS_WORKER_URL = "https://cdn.jsdelivr.net/npm/pdfjs-dist@4.10.38/build/pdf.worker.min.mjs";

let fflatePromise = null;
let pdfjsPromise = null;

function loadFflate() {
  if (!fflatePromise) fflatePromise = import(/* @vite-ignore */ FFLATE_URL);
  return fflatePromise;
}

function loadPdfjs() {
  if (!pdfjsPromise) {
    pdfjsPromise = import(/* @vite-ignore */ PDFJS_URL).then((mod) => {
      const api = mod && (mod.GlobalWorkerOptions ? mod : mod.default);
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
  const { unzipSync, strFromU8 } = await loadFflate();
  onProgress && onProgress(0.45, "Unpacking EPUB…");
  const unzipped = unzipSync(bytes, { filter: (f) => !f.name.endsWith("/") });

  const containerKey = Object.keys(unzipped).find((k) => k.endsWith("META-INF/container.xml"));
  let opfPath = null;
  if (containerKey) {
    const xml = new DOMParser().parseFromString(strFromU8(unzipped[containerKey]), "application/xml");
    const rootfile = xml.querySelector("rootfile");
    if (rootfile) opfPath = rootfile.getAttribute("full-path");
  }

  let title = stripExt(file.name);
  let author = "";
  let spineFiles = [];

  if (opfPath && unzipped[opfPath]) {
    const opfXml = new DOMParser().parseFromString(strFromU8(unzipped[opfPath]), "application/xml");
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
  }
  if (!spineFiles.length) {
    spineFiles = Object.keys(unzipped).filter((k) => /\.(x?html|htm)$/i.test(k));
  }

  const parts = [];
  for (let i = 0; i < spineFiles.length; i++) {
    const key = spineFiles[i];
    const data = unzipped[key] || unzipped[normalizeKey(unzipped, key)];
    if (!data) continue;
    try {
      const html = strFromU8(data);
      const text = stripHtmlToText(html);
      if (text.trim()) parts.push(text);
    } catch (_err) {
      // skip broken section, keep going
    }
    onProgress &&
      onProgress(
        0.55 + (i / Math.max(1, spineFiles.length)) * 0.4,
        `Section ${i + 1}/${spineFiles.length}`,
      );
  }
  const text = parts.join("\n\n").trim();
  onProgress && onProgress(1, `Loaded ${Math.round(text.length / 1000)} KB`);
  return { text, title, author, kind: "epub" };
}

async function parsePdf(file, onProgress) {
  onProgress && onProgress(0.05, "Reading PDF…");
  const bytes = await readFileWithProgress(file, (p) =>
    onProgress && onProgress(0.05 + p * 0.25, "Reading PDF…"),
  );
  const pdfjs = await loadPdfjs();
  onProgress && onProgress(0.35, "Parsing PDF…");
  const doc = await pdfjs.getDocument({ data: bytes }).promise;
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
    const page = await doc.getPage(p);
    const content = await page.getTextContent();
    let pageText = "";
    for (const item of content.items) {
      const s = String(item.str || "");
      pageText += s;
      pageText += item.hasEOL ? "\n" : " ";
    }
    parts.push(pageText.trim());
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
  onProgress && onProgress(1, `Loaded ${pageCount} pages`);
  return { text, title, author, kind: "pdf" };
}

export async function parseAnyFile(file, onProgress) {
  const name = (file.name || "").toLowerCase();
  const type = (file.type || "").toLowerCase();
  if (name.endsWith(".epub") || type.includes("epub")) return parseEpub(file, onProgress);
  if (name.endsWith(".pdf") || type.includes("pdf")) return parsePdf(file, onProgress);
  return parseTxt(file, onProgress);
}
