"use strict";

// Curated, hand-picked list of Microsoft "Neural" voices that sound the best
// for long-form narration. This powers the web audiobook maker voice picker.
// Ordering is intentional: the most natural/popular narrator voices come first.
const VOICES = [
  // English (US) - flagship voices (highest expressiveness first for best emotion results)
  {
    id: "en-US-AvaMultilingualNeural",
    label: "Ava (US, Female, Expressive)",
    locale: "en-US",
    gender: "female",
    style: "expressive",
    expressiveness: 0.92,
    recommendedStyles: ["natural", "conversational", "dramatic", "gentle"],
  },
  {
    id: "en-US-AndrewMultilingualNeural",
    label: "Andrew (US, Male, Warm)",
    locale: "en-US",
    gender: "male",
    style: "warm",
    expressiveness: 0.88,
    recommendedStyles: ["natural", "conversational", "gentle", "dramatic"],
  },
  {
    id: "en-US-EmmaMultilingualNeural",
    label: "Emma (US, Female, Friendly)",
    locale: "en-US",
    gender: "female",
    style: "friendly",
    expressiveness: 0.86,
    recommendedStyles: ["natural", "conversational", "gentle"],
  },
  {
    id: "en-US-AriaNeural",
    label: "Aria (US, Female, Conversational)",
    locale: "en-US",
    gender: "female",
    style: "conversational",
    expressiveness: 0.90,
    recommendedStyles: ["conversational", "natural", "gentle", "dramatic"],
  },
  {
    id: "en-US-BrianMultilingualNeural",
    label: "Brian (US, Male, Calm)",
    locale: "en-US",
    gender: "male",
    style: "calm",
    expressiveness: 0.82,
    recommendedStyles: ["natural", "gentle", "calm"],
  },
  {
    id: "en-US-GuyNeural",
    label: "Guy (US, Male, Narrator)",
    locale: "en-US",
    gender: "male",
    style: "narrator",
    expressiveness: 0.78,
    recommendedStyles: ["natural", "dramatic", "intense"],
  },
  {
    id: "en-US-JennyNeural",
    label: "Jenny (US, Female, Narrator)",
    locale: "en-US",
    gender: "female",
    style: "narrator",
    expressiveness: 0.79,
    recommendedStyles: ["natural", "conversational", "gentle"],
  },
  {
    id: "en-US-TonyNeural",
    label: "Tony (US, Male, Storyteller)",
    locale: "en-US",
    gender: "male",
    style: "storyteller",
    expressiveness: 0.84,
    recommendedStyles: ["natural", "dramatic", "conversational"],
  },
  {
    id: "en-US-DavisNeural",
    label: "Davis (US, Male, Newscaster)",
    locale: "en-US",
    gender: "male",
    style: "newscaster",
    expressiveness: 0.71,
    recommendedStyles: ["natural", "intense"],
  },
  {
    id: "en-US-JaneNeural",
    label: "Jane (US, Female, Bright)",
    locale: "en-US",
    gender: "female",
    style: "bright",
    expressiveness: 0.77,
    recommendedStyles: ["natural", "conversational", "excited"],
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
  },
  {
    id: "en-GB-RyanNeural",
    label: "Ryan (GB, Male, Natural)",
    locale: "en-GB",
    gender: "male",
    style: "natural",
    expressiveness: 0.83,
    recommendedStyles: ["natural", "dramatic", "gentle"],
  },
  {
    id: "en-GB-LibbyNeural",
    label: "Libby (GB, Female, Friendly)",
    locale: "en-GB",
    gender: "female",
    style: "friendly",
    expressiveness: 0.80,
    recommendedStyles: ["conversational", "gentle", "natural"],
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
  },
  {
    id: "en-AU-WilliamNeural",
    label: "William (AU, Male)",
    locale: "en-AU",
    gender: "male",
    style: "natural",
    expressiveness: 0.74,
    recommendedStyles: ["natural", "dramatic"],
  },
  {
    id: "en-IE-ConnorNeural",
    label: "Connor (IE, Male)",
    locale: "en-IE",
    gender: "male",
    style: "natural",
    expressiveness: 0.75,
    recommendedStyles: ["natural", "intense", "conversational"],
  },
  {
    id: "en-IE-EmilyNeural",
    label: "Emily (IE, Female)",
    locale: "en-IE",
    gender: "female",
    style: "natural",
    expressiveness: 0.77,
    recommendedStyles: ["natural", "gentle"],
  },
  {
    id: "en-IN-NeerjaNeural",
    label: "Neerja (IN, Female)",
    locale: "en-IN",
    gender: "female",
    style: "natural",
    expressiveness: 0.73,
    recommendedStyles: ["natural", "conversational"],
  },
  {
    id: "en-IN-PrabhatNeural",
    label: "Prabhat (IN, Male)",
    locale: "en-IN",
    gender: "male",
    style: "natural",
    expressiveness: 0.71,
    recommendedStyles: ["natural", "dramatic"],
  },

  // Other major languages (lower default express but still benefit from rich breaks/emphasis)
  { id: "es-ES-ElviraNeural", label: "Elvira (ES, Female)", locale: "es-ES", gender: "female", style: "natural", expressiveness: 0.68, recommendedStyles: ["natural", "conversational"] },
  { id: "es-MX-DaliaNeural", label: "Dalia (MX, Female)", locale: "es-MX", gender: "female", style: "natural", expressiveness: 0.67, recommendedStyles: ["natural", "gentle"] },
  { id: "fr-FR-DeniseNeural", label: "Denise (FR, Female)", locale: "fr-FR", gender: "female", style: "natural", expressiveness: 0.70, recommendedStyles: ["natural", "conversational", "gentle"] },
  { id: "fr-FR-HenriNeural", label: "Henri (FR, Male)", locale: "fr-FR", gender: "male", style: "natural", expressiveness: 0.69, recommendedStyles: ["natural", "dramatic"] },
  { id: "de-DE-KatjaNeural", label: "Katja (DE, Female)", locale: "de-DE", gender: "female", style: "natural", expressiveness: 0.66, recommendedStyles: ["natural", "intense"] },
  { id: "de-DE-ConradNeural", label: "Conrad (DE, Male)", locale: "de-DE", gender: "male", style: "natural", expressiveness: 0.65, recommendedStyles: ["natural", "dramatic"] },
  { id: "it-IT-ElsaNeural", label: "Elsa (IT, Female)", locale: "it-IT", gender: "female", style: "natural", expressiveness: 0.72, recommendedStyles: ["natural", "conversational", "gentle"] },
  { id: "pt-BR-FranciscaNeural", label: "Francisca (BR, Female)", locale: "pt-BR", gender: "female", style: "natural", expressiveness: 0.71, recommendedStyles: ["natural", "conversational"] },
  { id: "ja-JP-NanamiNeural", label: "Nanami (JP, Female)", locale: "ja-JP", gender: "female", style: "natural", expressiveness: 0.64, recommendedStyles: ["natural", "gentle"] },
  { id: "ko-KR-SunHiNeural", label: "Sun-Hi (KR, Female)", locale: "ko-KR", gender: "female", style: "natural", expressiveness: 0.63, recommendedStyles: ["natural", "conversational"] },
  { id: "zh-CN-XiaoxiaoNeural", label: "Xiaoxiao (CN, Female)", locale: "zh-CN", gender: "female", style: "natural", expressiveness: 0.70, recommendedStyles: ["natural", "gentle", "dramatic"] },
  { id: "zh-CN-YunxiNeural", label: "Yunxi (CN, Male)", locale: "zh-CN", gender: "male", style: "natural", expressiveness: 0.68, recommendedStyles: ["natural", "intense"] },
];

const DEFAULT_VOICE = "en-US-AvaMultilingualNeural";

function isValidVoiceId(voiceId) {
  if (typeof voiceId !== "string") return false;
  return VOICES.some((v) => v.id === voiceId);
}

module.exports = { VOICES, DEFAULT_VOICE, isValidVoiceId };
