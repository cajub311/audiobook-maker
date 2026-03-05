'use client';

import { motion } from 'framer-motion';
import { useInView } from 'framer-motion';
import { useRef, useState } from 'react';

const voices = [
  {
    character: 'Narrator',
    voice: 'en-US-GuyNeural',
    engine: 'Edge-TTS',
    accent: 'American',
    gender: 'Male',
    sample: '"The desert was the color of old bone, flat and featureless under a pale sky."',
    color: 'text-blue-400',
    dot: 'bg-blue-400',
    badge: 'bg-blue-500/10 border-blue-500/20 text-blue-300',
  },
  {
    character: 'Arlen',
    voice: 'en-GB-RyanNeural',
    engine: 'Edge-TTS',
    accent: 'British',
    gender: 'Male',
    sample: '"Demons fear the wards. I\'ve memorized every ward in the Warded Man\'s tome."',
    color: 'text-violet-400',
    dot: 'bg-violet-400',
    badge: 'bg-violet-500/10 border-violet-500/20 text-violet-300',
  },
  {
    character: 'Leesha',
    voice: 'en-US-JennyNeural',
    engine: 'Edge-TTS',
    accent: 'American',
    gender: 'Female',
    sample: '"My mother taught me that knowledge is the only ward that never fades."',
    color: 'text-pink-400',
    dot: 'bg-pink-400',
    badge: 'bg-pink-500/10 border-pink-500/20 text-pink-300',
  },
  {
    character: 'Rojer',
    voice: 'en-AU-WilliamNeural',
    engine: 'Edge-TTS',
    accent: 'Australian',
    gender: 'Male',
    sample: '"Music is a ward too. The corelings cannot resist it — they dance instead of attack."',
    color: 'text-amber-400',
    dot: 'bg-amber-400',
    badge: 'bg-amber-500/10 border-amber-500/20 text-amber-300',
  },
  {
    character: 'Jardir',
    voice: 'en-US-TonyNeural',
    engine: 'Edge-TTS',
    accent: 'American',
    gender: 'Male',
    sample: '"Everam\'s light guides the Deliverer. I am that light."',
    color: 'text-orange-400',
    dot: 'bg-orange-400',
    badge: 'bg-orange-500/10 border-orange-500/20 text-orange-300',
  },
];

const pronunciationOverrides = [
  { original: 'Jardir', override: 'JAR-deer' },
  { original: 'Leesha', override: 'LEE-sha' },
  { original: 'Everam', override: 'EH-veh-ram' },
  { original: 'alagai', override: 'al-ah-GUY' },
];

export default function VoiceDemo() {
  const ref = useRef(null);
  const isInView = useInView(ref, { once: true, margin: '-80px' });
  const [activeVoice, setActiveVoice] = useState(0);

  return (
    <section className="relative py-28 px-6" ref={ref}>
      <div className="max-w-6xl mx-auto">
        {/* Header */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={isInView ? { opacity: 1, y: 0 } : {}}
          transition={{ duration: 0.6 }}
          className="text-center mb-16"
        >
          <span className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-violet-600/10 border border-violet-500/20 text-violet-300 text-xs font-medium uppercase tracking-widest mb-4">
            Character voices
          </span>
          <h2 className="text-4xl md:text-5xl font-black text-white leading-tight">
            Every character has a{' '}
            <span className="gradient-text">unique voice</span>
          </h2>
          <p className="mt-4 text-slate-400 text-lg max-w-xl mx-auto">
            Automatic NLP character detection, manual assignment, and pronunciation control for fantasy names.
          </p>
        </motion.div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
          {/* Voice assignment card */}
          <motion.div
            initial={{ opacity: 0, x: -30 }}
            animate={isInView ? { opacity: 1, x: 0 } : {}}
            transition={{ duration: 0.7, delay: 0.1 }}
            className="rounded-2xl bg-[#0d1117] border border-white/8 overflow-hidden"
          >
            {/* Card header */}
            <div className="px-5 py-4 border-b border-white/5 flex items-center justify-between bg-[#161b22]">
              <div className="flex items-center gap-2">
                <div className="w-3 h-3 rounded-full bg-violet-500" />
                <span className="text-sm font-semibold text-white font-mono">voice_manifest.json</span>
              </div>
              <span className="text-xs text-slate-500 font-mono">5 characters</span>
            </div>

            {/* Voice list */}
            <div className="divide-y divide-white/5">
              {voices.map((v, i) => (
                <button
                  key={v.character}
                  onClick={() => setActiveVoice(i)}
                  className={`w-full px-5 py-4 text-left flex items-center gap-4 transition-all duration-200 ${
                    activeVoice === i ? 'bg-violet-600/8' : 'hover:bg-white/3'
                  }`}
                >
                  {/* Active indicator */}
                  <div className={`w-2 h-2 rounded-full flex-shrink-0 ${v.dot} ${activeVoice === i ? 'ring-2 ring-offset-1 ring-offset-[#0d1117]' : 'opacity-50'}`}
                    style={{ ringColor: v.dot }}
                  />

                  {/* Character info */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className={`font-semibold text-sm ${activeVoice === i ? v.color : 'text-white'}`}>
                        {v.character}
                      </span>
                      <span className={`text-[10px] px-1.5 py-0.5 rounded border font-medium ${v.badge}`}>
                        {v.accent}
                      </span>
                    </div>
                    <span className="text-xs text-slate-500 font-mono">{v.voice}</span>
                  </div>

                  {/* Engine badge */}
                  <span className="text-[10px] px-2 py-1 rounded-md bg-white/5 border border-white/8 text-slate-400 font-medium flex-shrink-0">
                    {v.engine}
                  </span>
                </button>
              ))}
            </div>

            {/* Footer */}
            <div className="px-5 py-3 border-t border-white/5 bg-[#161b22]/50 flex items-center justify-between">
              <span className="text-xs text-slate-500">Click a character to preview</span>
              <div className="flex items-center gap-1.5">
                <div className="w-1.5 h-1.5 rounded-full bg-green-400 animate-pulse" />
                <span className="text-xs text-slate-500">100+ voices available</span>
              </div>
            </div>
          </motion.div>

          {/* Right column */}
          <div className="space-y-5">
            {/* Sample text card */}
            <motion.div
              initial={{ opacity: 0, x: 30 }}
              animate={isInView ? { opacity: 1, x: 0 } : {}}
              transition={{ duration: 0.7, delay: 0.2 }}
              className="rounded-2xl bg-[#0d1117] border border-white/8 p-6"
            >
              <div className="flex items-center gap-3 mb-4">
                <div className={`w-10 h-10 rounded-xl ${voices[activeVoice].badge.split(' ')[0]} border ${voices[activeVoice].badge.split(' ')[1]} flex items-center justify-center`}>
                  <svg className={`w-5 h-5 ${voices[activeVoice].color}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
                  </svg>
                </div>
                <div>
                  <p className={`font-bold ${voices[activeVoice].color}`}>{voices[activeVoice].character}</p>
                  <p className="text-xs text-slate-500 font-mono">{voices[activeVoice].voice}</p>
                </div>
              </div>

              <blockquote className="text-slate-300 text-sm leading-relaxed italic border-l-2 border-violet-500/40 pl-4">
                {voices[activeVoice].sample}
              </blockquote>

              {/* Simulated waveform */}
              <div className="mt-4 flex items-center gap-1 h-8">
                {Array.from({ length: 40 }, (_, i) => (
                  <div
                    key={i}
                    className={`flex-1 rounded-full ${i % 3 === 0 ? voices[activeVoice].dot : 'bg-white/10'}`}
                    style={{
                      height: `${20 + Math.sin(i * 0.8) * 14 + Math.cos(i * 1.3) * 8}%`,
                      opacity: activeVoice === Math.floor(i / 8) ? 1 : 0.6,
                    }}
                  />
                ))}
              </div>
            </motion.div>

            {/* Pronunciation overrides */}
            <motion.div
              initial={{ opacity: 0, x: 30 }}
              animate={isInView ? { opacity: 1, x: 0 } : {}}
              transition={{ duration: 0.7, delay: 0.3 }}
              className="rounded-2xl bg-[#0d1117] border border-white/8 overflow-hidden"
            >
              <div className="px-5 py-3.5 border-b border-white/5 bg-[#161b22] flex items-center gap-2">
                <svg className="w-4 h-4 text-amber-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                </svg>
                <span className="text-sm font-semibold text-white">Pronunciation Overrides</span>
              </div>
              <div className="divide-y divide-white/5">
                {pronunciationOverrides.map(({ original, override }) => (
                  <div key={original} className="px-5 py-3 flex items-center justify-between font-mono text-sm">
                    <span className="text-slate-300">{original}</span>
                    <div className="flex items-center gap-2">
                      <svg className="w-3.5 h-3.5 text-violet-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 8l4 4m0 0l-4 4m4-4H3" />
                      </svg>
                      <span className="text-amber-300 font-medium">{override}</span>
                    </div>
                  </div>
                ))}
              </div>
            </motion.div>
          </div>
        </div>
      </div>
    </section>
  );
}
