"use strict";

// Curated, hand-picked list of Microsoft "Neural" voices that sound the best
// for long-form narration. This powers the web audiobook maker voice picker.
// Ordering is intentional: the most natural/popular narrator voices come first.
//
// Each voice now carries a capability descriptor:
//   supportsExpressAs: boolean   — whether <mstts:express-as style="..."> is honored
//   styles: string[]             — the EXACT express-as styles this voice supports
//
// IMPORTANT: Microsoft Edge's free Read-Aloud endpoint only honors
// `mstts:express-as` on a specific subset of voices, and each supporting voice
// only supports a specific set of styles. The flagship *Multilingual* voices
// (Ava, Andrew, Emma, Brian) do NOT support express-as styles at all — they are
// natively very expressive, so we rely on prosody/breaks/emphasis for them.
// Sending an unsupported style degrades/flattens output, so we never do it.

// Standard emotional style set shared by most expressive en-US single-locale voices.
const STANDARD_EMOTIONAL = [
  "angry", "cheerful", "excited", "friendly", "hopeful",
  "sad", "shouting", "terrified", "unfriendly", "whispering",
];

const VOICES = [
  // English (US) - flagship Multilingual voices (natively expressive, NO express-as)
  {
    id: "en-US-AvaMultilingualNeural",
    label: "Ava (US, Female, Expressive)",
    locale: "en-US",
    gender: "female",
    style: "expressive",
    expressiveness: 0.92,
    recommendedStyles: ["natural", "conversational", "dramatic", "gentle"],
    supportsExpressAs: false,
    styles: [],
  },
  {
    id: "en-US-AndrewMultilingualNeural",
    label: "Andrew (US, Male, Warm)",
    locale: "en-US",
    gender: "male",
    style: "warm",
    expressiveness: 0.88,
    recommendedStyles: ["natural", "conversational", "gentle", "dramatic"],
    supportsExpressAs: false,
    styles: [],
  },
  {
    id: "en-US-EmmaMultilingualNeural",
    label: "Emma (US, Female, Friendly)",
    locale: "en-US",
    gender: "female",
    style: "friendly",
    expressiveness: 0.86,
    recommendedStyles: ["natural", "conversational", "gentle"],
    supportsExpressAs: false,
    styles: [],
  },
  {
    id: "en-US-AriaNeural",
    label: "Aria (US, Female, Conversational)",
    locale: "en-US",
    gender: "female",
    style: "conversational",
    expressiveness: 0.90,
    recommendedStyles: ["conversational", "natural", "gentle", "dramatic"],
    supportsExpressAs: true,
    styles: [
      "chat", "customerservice", "narration-professional",
      "newscast-casual", "newscast-formal", "cheerful", "empathetic",
      "angry", "sad", "excited", "friendly", "terrified", "shouting",
      "unfriendly", "whispering", "hopeful",
    ],
  },
  {
    id: "en-US-BrianMultilingualNeural",
    label: "Brian (US, Male, Calm)",
    locale: "en-US",
    gender: "male",
    style: "calm",
    expressiveness: 0.82,
    recommendedStyles: ["natural", "gentle", "calm"],
    supportsExpressAs: false,
    styles: [],
  },
  {
    id: "en-US-GuyNeural",
    label: "Guy (US, Male, Narrator)",
    locale: "en-US",
    gender: "male",
    style: "narrator",
    expressiveness: 0.78,
    recommendedStyles: ["natural", "dramatic", "intense"],
    supportsExpressAs: true,
    styles: [
      "newscast", "angry", "cheerful", "sad", "excited", "friendly",
      "terrified", "shouting", "unfriendly", "whispering", "hopeful",
    ],
  },
  {
    id: "en-US-JennyNeural",
    label: "Jenny (US, Female, Narrator)",
    locale: "en-US",
    gender: "female",
    style: "narrator",
    expressiveness: 0.79,
    recommendedStyles: ["natural", "conversational", "gentle"],
    supportsExpressAs: true,
    styles: [
      "assistant", "chat", "customerservice", "newscast", "angry",
      "cheerful", "sad", "excited", "friendly", "terrified", "shouting",
      "unfriendly", "whispering", "hopeful",
    ],
  },
  {
    id: "en-US-TonyNeural",
    label: "Tony (US, Male, Storyteller)",
    locale: "en-US",
    gender: "male",
    style: "storyteller",
    expressiveness: 0.84,
    recommendedStyles: ["natural", "dramatic", "conversational"],
    supportsExpressAs: true,
    styles: STANDARD_EMOTIONAL.slice(),
  },
  {
    id: "en-US-DavisNeural",
    label: "Davis (US, Male, Newscaster)",
    locale: "en-US",
    gender: "male",
    style: "newscaster",
    expressiveness: 0.71,
    recommendedStyles: ["natural", "intense"],
    supportsExpressAs: true,
    styles: [
      "chat", "angry", "cheerful", "excited", "friendly", "hopeful",
      "sad", "shouting", "terrified", "unfriendly", "whispering",
    ],
  },
  {
    id: "en-US-JaneNeural",
    label: "Jane (US, Female, Bright)",
    locale: "en-US",
    gender: "female",
    style: "bright",
    expressiveness: 0.77,
    recommendedStyles: ["natural", "conversational", "excited"],
    supportsExpressAs: true,
    styles: STANDARD_EMOTIONAL.slice(),
  },

  // English (US) — additional expressive single-locale voices (NEW)
  {
    id: "en-US-SaraNeural",
    label: "Sara (US, Female, Warm)",
    locale: "en-US",
    gender: "female",
    style: "warm",
    expressiveness: 0.80,
    recommendedStyles: ["natural", "conversational", "gentle"],
    supportsExpressAs: true,
    styles: STANDARD_EMOTIONAL.slice(),
  },
  {
    id: "en-US-NancyNeural",
    label: "Nancy (US, Female, Expressive)",
    locale: "en-US",
    gender: "female",
    style: "expressive",
    expressiveness: 0.82,
    recommendedStyles: ["natural", "dramatic", "conversational"],
    supportsExpressAs: true,
    styles: STANDARD_EMOTIONAL.slice(),
  },
  {
    id: "en-US-ChristopherNeural",
    label: "Christopher (US, Male, Deep Narrator)",
    locale: "en-US",
    gender: "male",
    style: "narrator",
    expressiveness: 0.78,
    recommendedStyles: ["natural", "dramatic", "intense"],
    supportsExpressAs: true,
    styles: STANDARD_EMOTIONAL.slice(),
  },
  {
    id: "en-US-EricNeural",
    label: "Eric (US, Male, Mature)",
    locale: "en-US",
    gender: "male",
    style: "mature",
    expressiveness: 0.74,
    recommendedStyles: ["natural", "dramatic"],
    supportsExpressAs: true,
    styles: STANDARD_EMOTIONAL.slice(),
  },
  {
    id: "en-US-RogerNeural",
    label: "Roger (US, Male, Clear)",
    locale: "en-US",
    gender: "male",
    style: "clear",
    expressiveness: 0.73,
    recommendedStyles: ["natural", "conversational"],
    supportsExpressAs: true,
    styles: STANDARD_EMOTIONAL.slice(),
  },
  {
    id: "en-US-SteffanNeural",
    label: "Steffan (US, Male, Documentary)",
    locale: "en-US",
    gender: "male",
    style: "documentary",
    expressiveness: 0.75,
    recommendedStyles: ["natural", "dramatic", "intense"],
    supportsExpressAs: true,
    styles: STANDARD_EMOTIONAL.slice(),
  },

  // English (GB) — excellent for long-form
  {
    id: "en-GB-SoniaNeural",
    label: "Sonia (GB, Female, Natural)",
    locale: "en-GB",
    gender: "female",
    style: "natural",
    expressiveness: 0.85,
    recommendedStyles: ["natural", "gentle", "conversational"],
    supportsExpressAs: true,
    styles: ["cheerful", "sad"],
  },
  {
    id: "en-GB-RyanNeural",
    label: "Ryan (GB, Male, Natural)",
    locale: "en-GB",
    gender: "male",
    style: "natural",
    expressiveness: 0.83,
    recommendedStyles: ["natural", "dramatic", "gentle"],
    supportsExpressAs: true,
    styles: ["cheerful", "chat", "whispering", "sad"],
  },
  {
    id: "en-GB-LibbyNeural",
    label: "Libby (GB, Female, Friendly)",
    locale: "en-GB",
    gender: "female",
    style: "friendly",
    expressiveness: 0.80,
    recommendedStyles: ["conversational", "gentle", "natural"],
    supportsExpressAs: false,
    styles: [],
  },
  {
    id: "en-GB-ThomasNeural",
    label: "Thomas (GB, Male, Natural)",
    locale: "en-GB",
    gender: "male",
    style: "natural",
    expressiveness: 0.78,
    recommendedStyles: ["natural", "dramatic", "conversational"],
    supportsExpressAs: false,
    styles: [],
  },
  {
    id: "en-GB-MaisieNeural",
    label: "Maisie (GB, Female, Young)",
    locale: "en-GB",
    gender: "female",
    style: "young",
    expressiveness: 0.76,
    recommendedStyles: ["natural", "conversational", "gentle"],
    supportsExpressAs: false,
    styles: [],
  },

  // English (AU / IE / IN)
  {
    id: "en-AU-NatashaNeural",
    label: "Natasha (AU, Female)",
    locale: "en-AU",
    gender: "female",
    style: "natural",
    expressiveness: 0.76,
    recommendedStyles: ["natural", "conversational", "gentle"],
    supportsExpressAs: false,
    styles: [],
  },
  {
    id: "en-AU-WilliamNeural",
    label: "William (AU, Male)",
    locale: "en-AU",
    gender: "male",
    style: "natural",
    expressiveness: 0.74,
    recommendedStyles: ["natural", "dramatic"],
    supportsExpressAs: false,
    styles: [],
  },
  {
    id: "en-IE-ConnorNeural",
    label: "Connor (IE, Male)",
    locale: "en-IE",
    gender: "male",
    style: "natural",
    expressiveness: 0.75,
    recommendedStyles: ["natural", "intense", "conversational"],
    supportsExpressAs: false,
    styles: [],
  },
  {
    id: "en-IE-EmilyNeural",
    label: "Emily (IE, Female)",
    locale: "en-IE",
    gender: "female",
    style: "natural",
    expressiveness: 0.77,
    recommendedStyles: ["natural", "gentle"],
    supportsExpressAs: false,
    styles: [],
  },
  {
    id: "en-IN-NeerjaNeural",
    label: "Neerja (IN, Female)",
    locale: "en-IN",
    gender: "female",
    style: "natural",
    expressiveness: 0.73,
    recommendedStyles: ["natural", "conversational"],
    supportsExpressAs: true,
    styles: ["cheerful", "empathetic", "newscast"],
  },
  {
    id: "en-IN-PrabhatNeural",
    label: "Prabhat (IN, Male)",
    locale: "en-IN",
    gender: "male",
    style: "natural",
    expressiveness: 0.71,
    recommendedStyles: ["natural", "dramatic"],
    supportsExpressAs: false,
    styles: [],
  },

  // Other major languages (lower default express but still benefit from rich breaks/emphasis).
  // Style support for these is largely unknown/unsupported on the free endpoint, so we
  // disable express-as and rely purely on prosody + breaks + emphasis.
  { id: "es-ES-ElviraNeural", label: "Elvira (ES, Female)", locale: "es-ES", gender: "female", style: "natural", expressiveness: 0.68, recommendedStyles: ["natural", "conversational"], supportsExpressAs: false, styles: [] },
  { id: "es-MX-DaliaNeural", label: "Dalia (MX, Female)", locale: "es-MX", gender: "female", style: "natural", expressiveness: 0.67, recommendedStyles: ["natural", "gentle"], supportsExpressAs: false, styles: [] },
  { id: "fr-FR-DeniseNeural", label: "Denise (FR, Female)", locale: "fr-FR", gender: "female", style: "natural", expressiveness: 0.70, recommendedStyles: ["natural", "conversational", "gentle"], supportsExpressAs: false, styles: [] },
  { id: "fr-FR-HenriNeural", label: "Henri (FR, Male)", locale: "fr-FR", gender: "male", style: "natural", expressiveness: 0.69, recommendedStyles: ["natural", "dramatic"], supportsExpressAs: false, styles: [] },
  { id: "de-DE-KatjaNeural", label: "Katja (DE, Female)", locale: "de-DE", gender: "female", style: "natural", expressiveness: 0.66, recommendedStyles: ["natural", "intense"], supportsExpressAs: false, styles: [] },
  { id: "de-DE-ConradNeural", label: "Conrad (DE, Male)", locale: "de-DE", gender: "male", style: "natural", expressiveness: 0.65, recommendedStyles: ["natural", "dramatic"], supportsExpressAs: false, styles: [] },
  { id: "it-IT-ElsaNeural", label: "Elsa (IT, Female)", locale: "it-IT", gender: "female", style: "natural", expressiveness: 0.72, recommendedStyles: ["natural", "conversational", "gentle"], supportsExpressAs: false, styles: [] },
  { id: "pt-BR-FranciscaNeural", label: "Francisca (BR, Female)", locale: "pt-BR", gender: "female", style: "natural", expressiveness: 0.71, recommendedStyles: ["natural", "conversational"], supportsExpressAs: false, styles: [] },
  { id: "ja-JP-NanamiNeural", label: "Nanami (JP, Female)", locale: "ja-JP", gender: "female", style: "natural", expressiveness: 0.64, recommendedStyles: ["natural", "gentle"], supportsExpressAs: false, styles: [] },
  { id: "ko-KR-SunHiNeural", label: "Sun-Hi (KR, Female)", locale: "ko-KR", gender: "female", style: "natural", expressiveness: 0.63, recommendedStyles: ["natural", "conversational"], supportsExpressAs: false, styles: [] },
  { id: "zh-CN-XiaoxiaoNeural", label: "Xiaoxiao (CN, Female)", locale: "zh-CN", gender: "female", style: "natural", expressiveness: 0.70, recommendedStyles: ["natural", "gentle", "dramatic"], supportsExpressAs: true, styles: STANDARD_EMOTIONAL.slice() },
  { id: "zh-CN-YunxiNeural", label: "Yunxi (CN, Male)", locale: "zh-CN", gender: "male", style: "natural", expressiveness: 0.68, recommendedStyles: ["natural", "intense"], supportsExpressAs: true, styles: STANDARD_EMOTIONAL.slice() },
];

const DEFAULT_VOICE = "en-US-AvaMultilingualNeural";

const VOICE_INDEX = (() => {
  const m = new Map();
  for (const v of VOICES) m.set(v.id, v);
  return m;
})();

function isValidVoiceId(voiceId) {
  if (typeof voiceId !== "string") return false;
  return VOICE_INDEX.has(voiceId);
}

// Return the full voice metadata object for an id, or null if unknown.
function getVoiceMeta(voiceId) {
  if (typeof voiceId !== "string") return null;
  return VOICE_INDEX.get(voiceId) || null;
}

// Return true only if the given voice is known to support the given express-as style.
// Unknown voices / unknown styles => false (safe: caller will omit express-as).
function voiceSupportsStyle(voiceId, style) {
  const meta = getVoiceMeta(voiceId);
  if (!meta || !meta.supportsExpressAs || !Array.isArray(meta.styles)) return false;
  if (typeof style !== "string" || !style) return false;
  return meta.styles.indexOf(style.toLowerCase()) !== -1;
}

module.exports = {
  VOICES,
  DEFAULT_VOICE,
  isValidVoiceId,
  getVoiceMeta,
  voiceSupportsStyle,
};
