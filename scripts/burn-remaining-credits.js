#!/usr/bin/env node
/**
 * Burn Remaining ElevenLabs Free Credits
 * 
 * Usage:
 *   ELEVENLABS_API_KEY=sk_xxx node scripts/burn-remaining-credits.js
 * 
 * This script helps you intentionally use up the last of your free tier credits
 * with high-quality emotional test clips before the monthly reset.
 * 
 * It uses the same emotional presets that power the web app's quick test buttons.
 */

const https = require('https');
const fs = require('fs');
const path = require('path');

const API_KEY = process.env.ELEVENLABS_API_KEY;
if (!API_KEY) {
  console.error('❌ Missing ELEVENLABS_API_KEY environment variable');
  console.error('   Run like this:');
  console.error('   ELEVENLABS_API_KEY=sk-xxxxxxxx node scripts/burn-remaining-credits.js');
  process.exit(1);
}

const OUTPUT_DIR = path.join(__dirname, '..', 'burned-credits');
if (!fs.existsSync(OUTPUT_DIR)) fs.mkdirSync(OUTPUT_DIR, { recursive: true });

// These are the exact emotional micro-scenes from the web app's preset buttons.
// Short + high emotion = efficient credit usage + great test audio.
const PRESETS = [
  {
    name: 'whisper-heartbreak',
    voiceId: '21m00Tcm4TlvDq8ikWAM', // Rachel (very emotional on free tier)
    text: "She clutched the letter, tears welling. \"How could you do this to us?\" she whispered, voice trembling with heartbreak and disbelief.\n\nThe wind howled outside like a wounded animal.\n\nSuddenly the room fell deathly silent. It was the single most devastating moment of her life."
  },
  {
    name: 'furious-rage',
    voiceId: 'pNInz6obpgDQGcFmaJgB', // Adam (deep & angry)
    text: "\"Get out of my house this instant!\" he shouted furiously, face flushed with rage. \"I trusted you and you betrayed everything!\" His voice cracked with pure anger as he slammed the door."
  },
  {
    name: 'sudden-twist',
    voiceId: '21m00Tcm4TlvDq8ikWAM',
    text: "The letter slipped from her fingers. Suddenly the truth hit her like a physical blow — everything she believed was a lie. \"No... it can't be,\" she breathed."
  },
  {
    name: 'sarcastic-jab',
    voiceId: 'AZnzlk1XvdvUeBnXmlld', // Layla (great for dry/sarcastic)
    text: "She smiled sweetly. \"Oh sure, because that worked out so well last time, didn't it?\" The sarcasm dripped from every word. \"Yeah, brilliant plan. What could possibly go wrong?\""
  },
  {
    name: 'ecstatic-joy',
    voiceId: 'MF3mGyEYCl7XYWbV9V6O', // Elli (youthful energy)
    text: "\"We did it!\" she screamed with pure joy, jumping up and down. \"This is the most incredible, amazing, fantastic day of my entire life! I can't believe it actually happened!\""
  }
];

function synthesize(text, voiceId, modelId = 'eleven_turbo_v2_5') {
  return new Promise((resolve, reject) => {
    const data = JSON.stringify({
      text,
      model_id: modelId,
      voice_settings: {
        stability: 0.75,
        similarity_boost: 0.85,
        style: 0.65,
        use_speaker_boost: true
      }
    });

    const options = {
      hostname: 'api.elevenlabs.io',
      port: 443,
      path: `/v1/text-to-speech/${voiceId}`,
      method: 'POST',
      headers: {
        'Accept': 'audio/mpeg',
        'Content-Type': 'application/json',
        'xi-api-key': API_KEY,
        'Content-Length': Buffer.byteLength(data)
      }
    };

    const req = https.request(options, (res) => {
      if (res.statusCode !== 200) {
        let errorBody = '';
        res.on('data', chunk => errorBody += chunk);
        res.on('end', () => {
          reject(new Error(`ElevenLabs error ${res.statusCode}: ${errorBody}`));
        });
        return;
      }

      const chunks = [];
      res.on('data', chunk => chunks.push(chunk));
      res.on('end', () => {
        const audio = Buffer.concat(chunks);
        resolve({
          audio,
          usedChars: text.replace(/\s/g, '').length, // rough character count
          voiceId,
          model: modelId
        });
      });
    });

    req.on('error', reject);
    req.write(data);
    req.end();
  });
}

async function main() {
  console.log('🔥 ElevenLabs Free Credit Burner');
  console.log('   This will use your remaining free tier characters with rich emotional clips.\n');

  let totalUsed = 0;
  const maxToUse = 920; // Leave a tiny safety buffer for the 9%

  for (const preset of PRESETS) {
    const charCount = preset.text.replace(/\s/g, '').length;
    if (totalUsed + charCount > maxToUse) {
      console.log(`⏹️  Stopping — would exceed safe remaining budget (used ${totalUsed} chars)`);
      break;
    }

    console.log(`\n→ Generating "${preset.name}" (${charCount} chars) with voice ${preset.voiceId}...`);

    try {
      const result = await synthesize(preset.text, preset.voiceId);
      const filename = `${preset.name}-${Date.now()}.mp3`;
      const filepath = path.join(OUTPUT_DIR, filename);
      fs.writeFileSync(filepath, result.audio);

      totalUsed += charCount;
      console.log(`   ✅ Saved ${filename}  |  Used this run: ${charCount} chars  |  Total burned: ${totalUsed} chars`);
    } catch (err) {
      console.error(`   ❌ Failed: ${err.message}`);
      if (err.message.includes('quota') || err.message.includes('429')) {
        console.log('   → You hit the quota limit. All remaining credits are now used.');
        break;
      }
    }

    // Small delay to be nice to their rate limits
    await new Promise(r => setTimeout(r, 800));
  }

  console.log('\n🎉 Done burning credits.');
  console.log(`   Total characters used in this session: ${totalUsed}`);
  console.log(`   Files saved to: ${OUTPUT_DIR}`);
  console.log('\n   Check your ElevenLabs dashboard — you should now be at (or very close to) 0% free credits.');
  console.log('   Next month you get a fresh 10k.');
}

main().catch(console.error);