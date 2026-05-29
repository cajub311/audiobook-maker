# Voice Emotion Samples

Small, focused test corpus + generator for rapidly improving emotional delivery in the rich SSML engine.

## Purpose
- Exercise every major feature of the rich SSML builder used by the **free** (Edge neural) path:
  - `mstts:express-as` styles (sad, angry, cheerful/excited, whisper, terrified, empathetic…)
  - Per-segment auto emotion detection
  - Dialogue segmentation + `role="YoungAdultFemale"`
  - Question / exclamation prosody lifts
  - Strategic natural breaks (commas, em-dashes, ellipses, sentence boundaries)
  - Emphasis on loaded words (thresholded by expressiveness)
  - Paralinguistic hints (sighed, whispered, laughed…)
- Provide an easy A/B between **rich free path** and **basic/legacy path** (plus mock premium simulation).
- Give concrete, per-sample **listening notes** so you know exactly what to judge when you synthesize audio.
- Zero dependencies beyond the existing project. Pure Node. Fast feedback loop for tuning.

## Files
- `corpus.js` — 13 short, high-signal paragraphs (sad, angry, excited, sarcastic, whispering, dramatic, fear, gentle, mixed). Easy to edit or extend.
- `generate.js` — The runnable script. Generates rich vs basic SSML, computes mock ElevenLabs settings, prints a beautiful console report, and (with flag) writes artifacts.
- `outputs/` (created on `--write`) — individual `.ssml` files + per-sample reports + `FULL-REPORT.txt`.

The corpus and generator now also help validate the new per-speaker Role + Emotion Bias controls (from the dedicated agent): when multi-voice is enabled with different roles/biases per speaker, the rich SSML will include role= attributes and bias-adjusted express-as for distinct character voices. The generator itself is text-based but the builder fully supports the per-speaker hints (test by enabling multi-voice in the web UI with the samples).

## Run it

```bash
# Quick console report (recommended during active tuning)
node tests/voice-emotion-samples/generate.js

# Full artifacts for side-by-side editing / git diffing / feeding into TTS
node tests/voice-emotion-samples/generate.js --write
```

## How to use the output for voice tuning

1. **Run the script** after any change to `api/ssml-builder.js` (or the Python port in `tts/engines.py`).
2. **Read the listening notes** for the sample — they tell you exactly what the rich version *should* do differently.
3. **Synthesize**:
   - Easiest: open the web UI, paste the original TEXT, turn on "Debug" (Show generated SSML), generate, copy the rich SSML.
   - Or POST the text to `/api/tts` with `debugSSML: true`.
   - Or take a `*-free.ssml` file and feed it directly via `rawToStream` / `rawToFile` in `msedge-tts` (or the Python equivalent).
4. **Compare** the audio of rich vs basic (or rich vs previous version).
5. **Iterate**:
   - Too robotic on sadness? Raise `degreeFactor` or lower the expressiveness threshold in `detectEmotion`.
   - Whisper not quiet enough? Adjust the whisper rule or the degree scaling.
   - Dialogue not distinct? Tweak `getDialogueRole`.
   - Questions too cartoony? Dial back the +7Hz / +3% in the question block.
   - Over-emphasis on certain words? Change the word lists or the 0.36 / 0.68 expressiveness gates.

## Recommended workflow while tuning
- Keep a terminal open with `node tests/voice-emotion-samples/generate.js --write`
- Edit `api/ssml-builder.js`
- Re-run
- Spot-check 3–4 critical samples in audio (dramatic-01, whisper-01, heartbreak-01, and angry-question-01 are especially diagnostic)
- Commit only when the listening notes are satisfied across the corpus

## Extending the corpus
Just add objects to the array in `corpus.js`. Keep texts short (1–3 sentences). Include a mix of:
- Direct dialogue in quotes
- Trailing ? and !
- Em-dashes, ellipses, multiple punctuation
- Strong emotion keywords that match (or should match) `EMOTION_RULES`
- Mixed emotions in one paragraph

The script will automatically pick them up.

## Notes on "premium"
The real premium path (ElevenLabs) never sends SSML — it sends `voice_settings` (stability, style exaggeration, etc.). The script includes a faithful mock of the mapping used in production so you can see what the "more expensive" model would be asked to do for the same text + style + expressiveness. This helps decide whether a passage is worth the premium cost or whether the free rich SSML is already good enough.

---

Run it. Listen. Improve. Repeat. The goal is voices that actually *feel* the emotions instead of just describing them.
