"use strict";
// Lightweight A/B generator (rich vs basic) for quick console inspection
const { textToRichSSML } = require("../../api/ssml-builder");
const CORPUS = require("./corpus");

for (const s of CORPUS) {
  const rich = textToRichSSML(s.text, { style: s.defaultStyle, expressiveness: s.defaultExpress });
  console.log("\n=== " + s.id + " (" + s.category + ") ===");
  console.log("TEXT:", s.text);
  console.log("RICH:\n" + rich);
  console.log("NOTES:", s.listeningNotes);
}