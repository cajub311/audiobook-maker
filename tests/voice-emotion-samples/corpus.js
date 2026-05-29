module.exports = [
  {
    id: "sad-01",
    category: "sad",
    text: "I can't believe he's really gone. The house feels so empty without his laughter echoing through the halls.",
    defaultStyle: "sad",
    defaultExpress: 0.78,
    listeningNotes: "Rich should wrap with sad express-as + lowered energy. Listen for slower pacing and gentle emphasis on 'empty' and 'laughter'. Basic is flat and faster. Good test for melancholy timbre on Edge voices like Jenny or Sonia."
  },
  {
    id: "angry-01",
    category: "angry",
    text: 'How dare you speak to me like that! Get out of my house this instant!',
    defaultStyle: "angry",
    defaultExpress: 0.82,
    listeningNotes: "Strong angry express-as expected on the shout. Exclamation prosody should raise pitch+volume+emphasis. Dialogue segments get YoungAdultFemale role. Compare how basic lacks the style wrapper entirely — sounds like plain reading."
  },
  {
    id: "excited-01",
    category: "excited",
    text: "This is the most incredible thing that has ever happened to me! I can't wait to tell everyone!",
    defaultStyle: "excited",
    defaultExpress: 0.85,
    listeningNotes: "High cheerful/excited wrap + exclamation lifts. Energy and brightness should jump. Basic stays monotone."
  },
  {
    id: "sarcastic-01",
    category: "sarcastic",
    text: "Oh sure, because that always works out perfectly. Yeah right.",
    defaultStyle: "sarcastic",
    defaultExpress: 0.72,
    listeningNotes: "Sarcastic style + dry delivery. Slight downward pitch on the second sentence. Basic sounds sincere."
  },
  {
    id: "whisper-01",
    category: "whisper",
    text: "Don't tell anyone... but I think I know who did it. It was him, whispered under his breath.",
    defaultStyle: "whisper",
    defaultExpress: 0.65,
    listeningNotes: "whisper express-as + very low volume/intensity. The 'whispered' cue should trigger soft delivery. Basic is normal volume."
  },
  {
    id: "fear-01",
    category: "fear",
    text: "I was terrified. My hands were shaking and I could barely breathe as the footsteps got closer.",
    defaultStyle: "terrified",
    defaultExpress: 0.78,
    listeningNotes: "terrified style with trembling prosody. Faster breathing implied by short phrases + breaks."
  },
  {
    id: "dramatic-01",
    category: "dramatic",
    text: "Suddenly — everything changed. The letter fell from her hands and the room went completely silent.",
    defaultStyle: "dramatic",
    defaultExpress: 0.80,
    listeningNotes: "narration-professional + dramatic emphasis on 'Suddenly'. Long em-dash pause should be audible. Strong test of the break logic."
  },
  {
    id: "gentle-sad-01",
    category: "gentle",
    text: "She smiled softly and took his hand. 'It's going to be okay,' she said gently.",
    defaultStyle: "gentle",
    defaultExpress: 0.70,
    listeningNotes: "empathetic/gentle wrap. Warm, reassuring tone on the dialogue line. Role attribute should make it feel like a distinct caring character."
  },
  {
    id: "heartbreak-01",
    category: "sad",
    text: "After everything we promised each other? After all those years? She had never felt so completely and utterly alone.",
    defaultStyle: "sad",
    defaultExpress: 0.82,
    listeningNotes: "Multiple sad cues + question + 'utterly alone'. Should get the strongest sad express-as + slow pacing. One of the best diagnostic samples."
  },
  {
    id: "sarcastic-whisper-01",
    category: "sarcastic",
    text: "[whisper] Yeah... because trusting you worked out so well last time.",
    defaultStyle: "whisper",
    defaultExpress: 0.75,
    listeningNotes: "Inline [whisper] tag + sarcastic tone. The tag parser should turn it into an express-as even inside the segment."
  },
  {
    id: "dramatic-climax-01",
    category: "dramatic",
    text: "And in that moment — the single most devastating moment of her entire life — she finally understood.",
    defaultStyle: "dramatic",
    defaultExpress: 0.85,
    listeningNotes: "Heavy em-dashes + 'devastating' + 'finally understood'. Long pauses + sad/dramatic layering. Peak emotional test."
  },
];
