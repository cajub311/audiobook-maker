'use client';

import { motion } from 'framer-motion';
import { useInView } from 'framer-motion';
import { useRef } from 'react';

const steps = [
  {
    number: '01',
    title: 'Drop Your Book',
    description:
      'Upload an EPUB, PDF, or TXT file — or paste a web URL. The parser auto-detects chapters, extracts dialogue, and identifies character names using NLP.',
    details: [
      'Auto chapter detection',
      'Dialogue extraction & attribution',
      'Character NER via spaCy',
      'Pronunciation dictionary',
    ],
    icon: (
      <svg className="w-7 h-7" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
      </svg>
    ),
    visual: (
      <div className="rounded-xl bg-[#0d1117] border border-white/8 p-4 font-mono text-xs space-y-2">
        <div className="text-slate-500 mb-3">// Detected structure</div>
        <div className="flex items-center gap-2">
          <span className="text-emerald-400">✓</span>
          <span className="text-slate-300">12 chapters detected</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-emerald-400">✓</span>
          <span className="text-slate-300">847 dialogue lines</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-emerald-400">✓</span>
          <span className="text-slate-300">6 characters found</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-violet-400">→</span>
          <span className="text-slate-300">Arlen, Leesha, Rojer...</span>
        </div>
      </div>
    ),
  },
  {
    number: '02',
    title: 'Configure Voices',
    description:
      'Assign neural voices to each detected character. Choose between Edge-TTS (cloud, free, 100+ voices) or Kokoro (fully offline). Fine-tune pronunciation for fantasy or foreign names.',
    details: [
      'Per-character voice assignment',
      'Edge-TTS or Kokoro engine',
      'Pronunciation overrides',
      'Preview any voice instantly',
    ],
    icon: (
      <svg className="w-7 h-7" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
      </svg>
    ),
    visual: (
      <div className="rounded-xl bg-[#0d1117] border border-white/8 p-4 font-mono text-xs">
        <div className="text-slate-500 mb-3">// Voice assignments</div>
        <table className="w-full text-left">
          <tbody className="space-y-1">
            {[
              { char: 'Narrator', voice: 'en-US-GuyNeural', color: 'text-blue-400' },
              { char: 'Arlen', voice: 'en-GB-RyanNeural', color: 'text-violet-400' },
              { char: 'Leesha', voice: 'en-US-JennyNeural', color: 'text-pink-400' },
              { char: 'Rojer', voice: 'en-AU-WilliamNeural', color: 'text-amber-400' },
            ].map(({ char, voice, color }) => (
              <tr key={char}>
                <td className={`pr-3 pb-1.5 font-medium ${color}`}>{char}</td>
                <td className="text-slate-400 pb-1.5">{voice}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    ),
  },
  {
    number: '03',
    title: 'Generate & Download',
    description:
      'Click Generate. Watch real-time progress chapter by chapter. Download the finished M4B with embedded chapter markers, cover art, and EBU R128 -19 LUFS normalized audio.',
    details: [
      'Real-time chapter progress',
      'M4B with chapter markers',
      'EBU R128 loudness norm.',
      'Embedded cover art',
    ],
    icon: (
      <svg className="w-7 h-7" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
      </svg>
    ),
    visual: (
      <div className="rounded-xl bg-[#0d1117] border border-white/8 p-4 space-y-3">
        <div className="font-mono text-xs text-slate-500">// Generation progress</div>
        {[
          { label: 'Chapter 1 — The Desert Spear', pct: 100, done: true },
          { label: 'Chapter 2 — Deliverers', pct: 100, done: true },
          { label: 'Chapter 3 — The Painted Man', pct: 73, done: false },
        ].map(({ label, pct, done }) => (
          <div key={label} className="space-y-1">
            <div className="flex justify-between text-xs">
              <span className={done ? 'text-emerald-400' : 'text-slate-300'}>{label}</span>
              <span className={done ? 'text-emerald-400' : 'text-violet-400'}>{done ? '✓' : `${pct}%`}</span>
            </div>
            <div className="h-1 bg-white/5 rounded-full overflow-hidden">
              <div
                className={`h-full rounded-full ${done ? 'bg-emerald-500' : 'bg-violet-500 animate-pulse'}`}
                style={{ width: `${pct}%` }}
              />
            </div>
          </div>
        ))}
      </div>
    ),
  },
];

export default function HowItWorks() {
  const ref = useRef(null);
  const isInView = useInView(ref, { once: true, margin: '-80px' });

  return (
    <section id="how-it-works" className="relative py-28 px-6" ref={ref}>
      {/* Background accent */}
      <div className="absolute inset-0 -z-10">
        <div className="absolute inset-0 bg-gradient-to-b from-transparent via-violet-950/20 to-transparent" />
      </div>

      <div className="max-w-6xl mx-auto">
        {/* Header */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={isInView ? { opacity: 1, y: 0 } : {}}
          transition={{ duration: 0.6 }}
          className="text-center mb-20"
        >
          <span className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-violet-600/10 border border-violet-500/20 text-violet-300 text-xs font-medium uppercase tracking-widest mb-4">
            Simple workflow
          </span>
          <h2 className="text-4xl md:text-5xl font-black text-white leading-tight">
            Three steps to your{' '}
            <span className="gradient-text">audiobook</span>
          </h2>
          <p className="mt-4 text-slate-400 text-lg max-w-xl mx-auto">
            From raw file to polished M4B in minutes. No command line, no configuration files.
          </p>
        </motion.div>

        {/* Steps */}
        <div className="space-y-16">
          {steps.map((step, index) => (
            <motion.div
              key={step.number}
              initial={{ opacity: 0, x: index % 2 === 0 ? -40 : 40 }}
              animate={isInView ? { opacity: 1, x: 0 } : {}}
              transition={{ duration: 0.7, delay: index * 0.15, ease: [0.25, 0.46, 0.45, 0.94] }}
              className={`flex flex-col ${index % 2 === 1 ? 'lg:flex-row-reverse' : 'lg:flex-row'} gap-10 items-center`}
            >
              {/* Text side */}
              <div className="flex-1 space-y-6">
                {/* Step badge */}
                <div className="flex items-center gap-4">
                  <div className="relative">
                    <div className="w-14 h-14 rounded-2xl bg-violet-600/15 border border-violet-500/30 flex items-center justify-center text-violet-400">
                      {step.icon}
                    </div>
                    <div className="absolute -top-2 -right-2 w-6 h-6 rounded-full bg-violet-600 border-2 border-[#020817] flex items-center justify-center">
                      <span className="text-white text-[10px] font-black">{index + 1}</span>
                    </div>
                  </div>
                  <div>
                    <span className="text-violet-400 text-xs font-mono font-bold tracking-widest">STEP {step.number}</span>
                    <h3 className="text-2xl md:text-3xl font-black text-white">{step.title}</h3>
                  </div>
                </div>

                <p className="text-slate-400 text-base md:text-lg leading-relaxed">{step.description}</p>

                {/* Detail list */}
                <ul className="space-y-2">
                  {step.details.map((detail) => (
                    <li key={detail} className="flex items-center gap-3 text-sm text-slate-300">
                      <div className="w-5 h-5 rounded-full bg-violet-600/20 border border-violet-500/30 flex items-center justify-center flex-shrink-0">
                        <svg className="w-3 h-3 text-violet-400" fill="currentColor" viewBox="0 0 20 20">
                          <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                        </svg>
                      </div>
                      {detail}
                    </li>
                  ))}
                </ul>
              </div>

              {/* Visual side */}
              <div className="flex-1 w-full max-w-md">
                <div className="relative">
                  <div className="absolute inset-0 bg-violet-600/10 blur-3xl rounded-2xl scale-90 -z-10" />
                  {step.visual}
                </div>
              </div>
            </motion.div>
          ))}
        </div>

        {/* Flow connector */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={isInView ? { opacity: 1, y: 0 } : {}}
          transition={{ duration: 0.6, delay: 0.6 }}
          className="mt-20 flex items-center justify-center"
        >
          <div className="flex items-center gap-3 px-6 py-3 rounded-full bg-violet-600/10 border border-violet-500/20">
            {['Parse', '→', 'Generate', '→', 'Assemble'].map((item, i) => (
              <span
                key={i}
                className={`text-sm font-medium ${item === '→' ? 'text-violet-500' : 'text-violet-300'}`}
              >
                {item}
              </span>
            ))}
          </div>
        </motion.div>
      </div>
    </section>
  );
}
