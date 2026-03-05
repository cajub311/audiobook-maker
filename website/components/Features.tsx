'use client';

import { motion } from 'framer-motion';
import { useInView } from 'framer-motion';
import { useRef } from 'react';

const features = [
  {
    icon: (
      <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z" />
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M14 3v4a1 1 0 001 1h4" />
      </svg>
    ),
    title: 'Multi-Format Input',
    description:
      'Ingest EPUB, PDF, TXT files, or any web URL. The smart parser auto-detects chapters, headings, and paragraph structure across all formats.',
    tags: ['EPUB', 'PDF', 'TXT', 'URL'],
    color: 'from-blue-500/20 to-blue-600/5',
    border: 'border-blue-500/20',
    iconBg: 'bg-blue-500/15 text-blue-400',
  },
  {
    icon: (
      <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0z" />
      </svg>
    ),
    title: 'Smart Character Voices',
    description:
      'NLP-powered character detection automatically assigns unique neural voices per character using spaCy named entity recognition. Customize or override any assignment.',
    tags: ['spaCy NER', 'Edge-TTS', '100+ voices'],
    color: 'from-violet-500/20 to-violet-600/5',
    border: 'border-violet-500/20',
    iconBg: 'bg-violet-500/15 text-violet-400',
  },
  {
    icon: (
      <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17H3a2 2 0 01-2-2V5a2 2 0 012-2h14a2 2 0 012 2v3" />
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M15 11a3 3 0 11-6 0 3 3 0 016 0z" />
      </svg>
    ),
    title: 'Offline-First',
    description:
      'Kokoro ONNX TTS runs entirely on your CPU — no internet, no API keys, no cloud dependency. Your books and their content stay completely private.',
    tags: ['Kokoro ONNX', 'CPU only', '100% Private'],
    color: 'from-emerald-500/20 to-emerald-600/5',
    border: 'border-emerald-500/20',
    iconBg: 'bg-emerald-500/15 text-emerald-400',
  },
  {
    icon: (
      <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4" />
      </svg>
    ),
    title: 'Manifest Pipeline',
    description:
      'Every synthesized audio segment is cached. Stop mid-generation, change a voice, and resume — only modified segments are re-generated. No wasted time.',
    tags: ['Resumable', 'Cached segments', 'Smart diff'],
    color: 'from-amber-500/20 to-amber-600/5',
    border: 'border-amber-500/20',
    iconBg: 'bg-amber-500/15 text-amber-400',
  },
  {
    icon: (
      <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 19V6l12-3v13M9 19c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zm12-3c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zM9 10l12-3" />
      </svg>
    ),
    title: 'Professional Audio',
    description:
      'Two-pass EBU R128 loudness normalization at -19 LUFS. Output as M4B with embedded chapters and cover art, or MP3 for maximum compatibility.',
    tags: ['-19 LUFS', 'M4B chapters', 'Cover art'],
    color: 'from-pink-500/20 to-pink-600/5',
    border: 'border-pink-500/20',
    iconBg: 'bg-pink-500/15 text-pink-400',
  },
  {
    icon: (
      <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" />
      </svg>
    ),
    title: 'Open Source & Free',
    description:
      'MIT licensed. Edge-TTS uses Microsoft\'s cloud TTS at zero cost. Kokoro is fully open-source. No subscriptions, no account creation required.',
    tags: ['MIT License', 'Edge-TTS free', 'Community'],
    color: 'from-cyan-500/20 to-cyan-600/5',
    border: 'border-cyan-500/20',
    iconBg: 'bg-cyan-500/15 text-cyan-400',
  },
];

const containerVariants = {
  hidden: {},
  visible: {
    transition: {
      staggerChildren: 0.1,
    },
  },
};

const cardVariants = {
  hidden: { opacity: 0, y: 40 },
  visible: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.6, ease: [0.25, 0.46, 0.45, 0.94] },
  },
};

export default function Features() {
  const ref = useRef(null);
  const isInView = useInView(ref, { once: true, margin: '-100px' });

  return (
    <section id="features" className="relative py-28 px-6" ref={ref}>
      {/* Section divider */}
      <div className="absolute top-0 left-1/2 -translate-x-1/2 w-px h-24 bg-gradient-to-b from-transparent via-violet-500/30 to-transparent" />

      <div className="max-w-6xl mx-auto">
        {/* Header */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={isInView ? { opacity: 1, y: 0 } : {}}
          transition={{ duration: 0.6 }}
          className="text-center mb-16"
        >
          <span className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-violet-600/10 border border-violet-500/20 text-violet-300 text-xs font-medium uppercase tracking-widest mb-4">
            Everything you need
          </span>
          <h2 className="text-4xl md:text-5xl font-black text-white leading-tight">
            Packed with{' '}
            <span className="gradient-text">powerful features</span>
          </h2>
          <p className="mt-4 text-slate-400 text-lg max-w-2xl mx-auto">
            From multi-format ingestion to studio-quality output — every step of the audiobook pipeline is covered.
          </p>
        </motion.div>

        {/* Grid */}
        <motion.div
          variants={containerVariants}
          initial="hidden"
          animate={isInView ? 'visible' : 'hidden'}
          className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5"
        >
          {features.map((feature) => (
            <motion.div
              key={feature.title}
              variants={cardVariants}
              className={`relative group rounded-2xl p-6 bg-gradient-to-br ${feature.color} border ${feature.border} hover:border-opacity-40 transition-all duration-300 cursor-default overflow-hidden`}
            >
              {/* Hover glow */}
              <div className="absolute inset-0 opacity-0 group-hover:opacity-100 transition-opacity duration-500 bg-gradient-to-br from-white/[0.02] to-transparent rounded-2xl" />

              {/* Icon */}
              <div className={`w-11 h-11 rounded-xl ${feature.iconBg} flex items-center justify-center mb-4 transition-transform duration-300 group-hover:scale-110`}>
                {feature.icon}
              </div>

              {/* Content */}
              <h3 className="text-lg font-bold text-white mb-2">{feature.title}</h3>
              <p className="text-sm text-slate-400 leading-relaxed mb-4">{feature.description}</p>

              {/* Tags */}
              <div className="flex flex-wrap gap-1.5">
                {feature.tags.map((tag) => (
                  <span
                    key={tag}
                    className="px-2 py-0.5 rounded-md bg-white/5 border border-white/8 text-xs text-slate-300 font-medium"
                  >
                    {tag}
                  </span>
                ))}
              </div>
            </motion.div>
          ))}
        </motion.div>
      </div>
    </section>
  );
}
