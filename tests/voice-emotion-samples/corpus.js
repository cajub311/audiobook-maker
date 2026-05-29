"use strict";

/**
 * Emotional Test Corpus for voice tuning.
 * 13 short paragraphs designed to exercise:
 * - Dialogue detection + role=YoungAdultFemale
 * - Questions (? → pitch lift)
 * - Exclamations (! → volume + emphasis + pitch)
 * - Auto emotion detection (sad/angry/excited/whisper/etc via keywords + cues)
 * - EMOTION_RULES (mstts:express-as)
 * - Strategic breaks (commas, em-dashes, ellipses, sentence ends)
 * - Emphasis on loaded words
 * - Paralinguistic hints (sighed, whispered, etc.)
 * - Mixed emotions in one passage
 *
 * Each item is short on purpose so full SSML is easy to inspect + synthesize.
 */

module.exports = [
  {
    id: "sad-01",
    category: "sad",
    text: "I can't believe he's really gone. The house feels so empty without his laughter echoing through the halls.",
    defaultStyle: "sad",
    defaultExpress: 0.72,
    listeningNotes: "Rich should wrap with sad express-as + lowered energy. Listen for slower pacing and gentle emphasis on 'empty' and 'laughter'. Basic is flat and faster. Good test for melancholy timbre on Edge voices like Jenny or Sonia."
  },
  {
    id: "angry-01",
    category: "angry",
    text: "How dare you speak to me like that! Get out of my house this instant!",
    defaultStyle: "angry",
    defaultExpress: 0.78,
    listeningNotes: "Strong angry express-as expected on the shout. Exclamation prosody should raise pitch+volume+emphasis. Dialogue segments get YoungAdultFemale role. Compare how basic lacks the style wrapper entirely — sounds like plain reading."
  },
  {
    id: "excited-01",
    category: "excited",
    text: "Can you believe it? We actually won! This is the most amazing day of my life!",
    defaultStyle: "excited",
    defaultExpress: 0.82,
    listeningNotes: "Multiple ! and 'amazing' should trigger cheerful/excited express-as + lifted prosody on exclamations and the question. High energy, faster rate on peaks. Listen for the joy vs the flat delivery in basic path."
  },
  {
    id: "sarcastic-01",
    category: "sarcastic",
    text: "Oh sure, because that's exactly what I wanted to hear today. Perfect. Just perfect.",
    defaultStyle: "auto",
    defaultExpress: 0.65,
    listeningNotes: "Auto detector may pick sarcastic from 'sure' + 'of course' cues. Rich adds moderate express + ironic pauses via breaks. The repeated 'Perfect' may get emphasis. Basic sounds sincere and even — the opposite of intent."
  },
  {
    id: "whisper-01",
    category: "whisper",
    text: "Don't tell anyone this, but I think I saw something move in the shadows just now.",
    defaultStyle: "auto",
    defaultExpress: 0.58,
    listeningNotes: "Whisper cues ('whisper' not present but 'Don't tell anyone' + secret feel) should produce whisper or empathetic style + reduced degree. Softer volume, extra micro-breaks. Critical test: does the voice actually drop to a hushed delivery?"
  },
  {
    id: "dramatic-01",
    category: "dramatic",
    text: "The old wizard raised his staff high. \"You shall not pass!\" he cried, his voice booming through the abyss. Lightning cracked and the bridge began to crumble.",
    defaultStyle: "dramatic",
    defaultExpress: 0.80,
    listeningNotes: "Dialogue trigger + dramatic style = narration-professional wrapper + cheerful/excited on the shouted line + role attribute. Strong breaks around em-dashes/periods. Listen for theatrical weight and distinct 'character voice' shift on the quote. One of the best showcases of layered richness."
  },
  {
    id: "fear-01",
    category: "fear",
    text: "Is someone there? I... I heard footsteps. Please... don't come any closer.",
    defaultStyle: "auto",
    defaultExpress: 0.70,
    listeningNotes: "Fear keywords + questions + ellipses + pleading should activate terrified style + reduced emphasis on 'please'. Trembling effect via breaks and prosody. Question gets the +7Hz lift. Excellent for testing scared delivery without over-acting."
  },
  {
    id: "gentle-sad-01",
    category: "gentle + sad",
    text: "She smiled softly and touched his cheek. \"I will always remember you,\" she whispered, her voice full of gentle sadness. The rain fell like quiet tears.",
    defaultStyle: "gentle",
    defaultExpress: 0.65,
    listeningNotes: "Gentle + sad cues compete; 'whispered' + 'softly' + 'sadness' should produce empathetic/sad wrappers + dialogue role. Very important for tender scenes. Rich version feels human and caring; basic is clinical."
  },
  {
    id: "excited-multi-01",
    category: "excited",
    text: "Yes! Yes! We did it! I knew we could! This changes everything for us!",
    defaultStyle: "excited",
    defaultExpress: 0.85,
    listeningNotes: "Rapid exclamations test how well the builder stacks emphasis + cheerful express-as + exclamation prosody without sounding cartoonish. High expressiveness here. Check that rate doesn't go too wild."
  },
  {
    id: "angry-question-01",
    category: "angry",
    text: "What were you thinking when you did that? Did you honestly believe no one would ever find out?",
    defaultStyle: "angry",
    defaultExpress: 0.75,
    listeningNotes: "Two questions + angry keywords. Should get angry express-as around the whole + question-specific pitch lifts. Feels accusatory and heated. Basic path loses all the interrogative lift and rage coloring."
  },
  {
    id: "heartbreak-01",
    category: "sad + gentle",
    text: "I thought we had more time. Please... just stay a little longer. I don't know how to do this without you.",
    defaultStyle: "sad",
    defaultExpress: 0.78,
    listeningNotes: "Heartbreak + pleading + ellipses. Rich should deliver quiet devastation (sad + empathetic) with very human micro-pauses. One of the most moving samples when the voice actually sounds like it cares."
  },
  {
    id: "sarcastic-whisper-01",
    category: "sarcastic + whisper",
    text: "Oh, you're *definitely* the expert here. Go on then... tell us all how it's done.",
    defaultStyle: "sarcastic",
    defaultExpress: 0.70,
    listeningNotes: "Mixed tone (sarcastic delivery of a whisper challenge). Good test of competing rules + emphasis on 'definitely' and 'expert'. Rich should feel cutting but hushed."
  },
  {
    id: "dramatic-climax-01",
    category: "dramatic + fear + angry",
    text: "No — listen to me! If we turn back now, everything we fought for dies here. Do you understand? We finish this tonight!",
    defaultStyle: "dramatic",
    defaultExpress: 0.88,
    listeningNotes: "Multi-sentence emotional arc (fear → determination → rallying cry). Rich SSML should shift styles mid-paragraph. The 'No' + em-dash + final ! is a killer test for dynamic delivery."
  }
];