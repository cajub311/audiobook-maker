"use strict";

// Curated, hand-picked list of Microsoft "Neural" voices that sound the best
// for long-form narration. This powers the web audiobook maker voice picker.
// Ordering is intentional: the most natural/popular narrator voices come first.
const VOICES = [
  // English (US) - flagship voices
  { id: "en-US-AvaMultilingualNeural", label: "Ava (US, Female, Expressive)", locale: "en-US", gender: "female", style: "expressive" },
  { id: "en-US-AndrewMultilingualNeural", label: "Andrew (US, Male, Warm)", locale: "en-US", gender: "male", style: "warm" },
  { id: "en-US-EmmaMultilingualNeural", label: "Emma (US, Female, Friendly)", locale: "en-US", gender: "female", style: "friendly" },
  { id: "en-US-BrianMultilingualNeural", label: "Brian (US, Male, Calm)", locale: "en-US", gender: "male", style: "calm" },
  { id: "en-US-GuyNeural", label: "Guy (US, Male, Narrator)", locale: "en-US", gender: "male", style: "narrator" },
  { id: "en-US-JennyNeural", label: "Jenny (US, Female, Narrator)", locale: "en-US", gender: "female", style: "narrator" },
  { id: "en-US-AriaNeural", label: "Aria (US, Female, Conversational)", locale: "en-US", gender: "female", style: "conversational" },
  { id: "en-US-DavisNeural", label: "Davis (US, Male, Newscaster)", locale: "en-US", gender: "male", style: "newscaster" },
  { id: "en-US-TonyNeural", label: "Tony (US, Male, Storyteller)", locale: "en-US", gender: "male", style: "storyteller" },
  { id: "en-US-JaneNeural", label: "Jane (US, Female, Bright)", locale: "en-US", gender: "female", style: "bright" },

  // English (GB)
  { id: "en-GB-RyanNeural", label: "Ryan (GB, Male, Natural)", locale: "en-GB", gender: "male", style: "natural" },
  { id: "en-GB-SoniaNeural", label: "Sonia (GB, Female, Natural)", locale: "en-GB", gender: "female", style: "natural" },
  { id: "en-GB-LibbyNeural", label: "Libby (GB, Female, Friendly)", locale: "en-GB", gender: "female", style: "friendly" },

  // English (AU / IE / IN)
  { id: "en-AU-NatashaNeural", label: "Natasha (AU, Female)", locale: "en-AU", gender: "female", style: "natural" },
  { id: "en-AU-WilliamNeural", label: "William (AU, Male)", locale: "en-AU", gender: "male", style: "natural" },
  { id: "en-IE-ConnorNeural", label: "Connor (IE, Male)", locale: "en-IE", gender: "male", style: "natural" },
  { id: "en-IE-EmilyNeural", label: "Emily (IE, Female)", locale: "en-IE", gender: "female", style: "natural" },
  { id: "en-IN-NeerjaNeural", label: "Neerja (IN, Female)", locale: "en-IN", gender: "female", style: "natural" },
  { id: "en-IN-PrabhatNeural", label: "Prabhat (IN, Male)", locale: "en-IN", gender: "male", style: "natural" },

  // Other major languages
  { id: "es-ES-ElviraNeural", label: "Elvira (ES, Female)", locale: "es-ES", gender: "female", style: "natural" },
  { id: "es-MX-DaliaNeural", label: "Dalia (MX, Female)", locale: "es-MX", gender: "female", style: "natural" },
  { id: "fr-FR-DeniseNeural", label: "Denise (FR, Female)", locale: "fr-FR", gender: "female", style: "natural" },
  { id: "fr-FR-HenriNeural", label: "Henri (FR, Male)", locale: "fr-FR", gender: "male", style: "natural" },
  { id: "de-DE-KatjaNeural", label: "Katja (DE, Female)", locale: "de-DE", gender: "female", style: "natural" },
  { id: "de-DE-ConradNeural", label: "Conrad (DE, Male)", locale: "de-DE", gender: "male", style: "natural" },
  { id: "it-IT-ElsaNeural", label: "Elsa (IT, Female)", locale: "it-IT", gender: "female", style: "natural" },
  { id: "pt-BR-FranciscaNeural", label: "Francisca (BR, Female)", locale: "pt-BR", gender: "female", style: "natural" },
  { id: "ja-JP-NanamiNeural", label: "Nanami (JP, Female)", locale: "ja-JP", gender: "female", style: "natural" },
  { id: "ko-KR-SunHiNeural", label: "Sun-Hi (KR, Female)", locale: "ko-KR", gender: "female", style: "natural" },
  { id: "zh-CN-XiaoxiaoNeural", label: "Xiaoxiao (CN, Female)", locale: "zh-CN", gender: "female", style: "natural" },
  { id: "zh-CN-YunxiNeural", label: "Yunxi (CN, Male)", locale: "zh-CN", gender: "male", style: "natural" },
];

const DEFAULT_VOICE = "en-US-AvaMultilingualNeural";

function isValidVoiceId(voiceId) {
  if (typeof voiceId !== "string") return false;
  return VOICES.some((v) => v.id === voiceId);
}

module.exports = { VOICES, DEFAULT_VOICE, isValidVoiceId };
