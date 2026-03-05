'use client';

import { motion } from 'framer-motion';
import { useInView } from 'framer-motion';
import { useRef } from 'react';

const technologies = [
  {
    name: 'Python',
    description: 'Core engine — parsing, orchestration, and pipeline management.',
    version: '3.10+',
    color: 'from-blue-500/20 to-yellow-500/10',
    border: 'border-blue-500/20',
    textColor: 'text-blue-400',
    icon: (
      <svg viewBox="0 0 24 24" className="w-8 h-8 fill-current">
        <path d="M14.25.18l.9.2.73.26.59.3.45.32.34.34.25.34.16.33.1.3.04.26.02.2-.01.13V8.5l-.05.63-.13.55-.21.46-.26.38-.3.31-.33.25-.35.19-.35.14-.33.1-.3.07-.26.04-.23.01h-8l-.44.05-.37.14-.35.26-.29.38-.28.57-.26.91-.1 1.02-.06 1.17-.02 1.3.04 1.39.09 1.46.15 1.49.21 1.5.28 1.46.36 1.39.46 1.28.58 1.11.7.9.83.65.97.36 1.11.05 1.22-.25 1.31-.57 1.38-.87 1.42-1.14 1.44-1.36 1.43-1.55 1.38-1.67 1.3-1.76 1.16-1.81.98-1.82.76-1.78.5-1.69.22-1.55-.06-1.37-.35-1.14-.67-.88-1-.57-1.32-.22-1.6.16-1.83.57-2.02.96-2.15 1.35-2.21 1.72-2.18 2.04-2.07 2.33-1.87 2.56-1.58 2.74-1.23 2.83-.82 2.83-.37 2.75.11 2.55.62 2.27 1.14 1.91 1.64 1.48 2.12.98 2.56.42 2.95zm-9.3 15.57c.2.2.33.45.38.72.05.27.03.54-.07.79-.1.25-.26.46-.46.62-.21.16-.46.25-.73.28-.27.03-.53-.02-.77-.14-.24-.12-.44-.3-.58-.53-.14-.23-.2-.49-.18-.75.02-.26.11-.51.25-.73.14-.22.33-.39.56-.51.23-.12.48-.17.73-.15.25.02.49.11.69.28l.18.12zm10.08 0c.2.2.33.45.38.72.05.27.03.54-.07.79-.1.25-.26.46-.46.62-.21.16-.46.25-.73.28-.27.03-.53-.02-.77-.14-.24-.12-.44-.3-.58-.53-.14-.23-.2-.49-.18-.75.02-.26.11-.51.25-.73.14-.22.33-.39.56-.51.23-.12.48-.17.73-.15.25.02.49.11.69.28l.18.12z"/>
      </svg>
    ),
  },
  {
    name: 'Edge-TTS',
    description: "Microsoft's free cloud neural TTS. 100+ voices, zero cost, no API key.",
    version: 'Cloud',
    color: 'from-cyan-500/20 to-blue-500/10',
    border: 'border-cyan-500/20',
    textColor: 'text-cyan-400',
    icon: (
      <svg viewBox="0 0 24 24" className="w-8 h-8 fill-current">
        <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 14.5v-9l6 4.5-6 4.5z"/>
      </svg>
    ),
  },
  {
    name: 'Kokoro',
    description: 'Open-source ONNX TTS model. Runs fully offline on CPU — no GPU required.',
    version: 'ONNX',
    color: 'from-emerald-500/20 to-green-500/10',
    border: 'border-emerald-500/20',
    textColor: 'text-emerald-400',
    icon: (
      <svg viewBox="0 0 24 24" className="w-8 h-8 fill-current">
        <path d="M12 3v10.55c-.59-.34-1.27-.55-2-.55-2.21 0-4 1.79-4 4s1.79 4 4 4 4-1.79 4-4V7h4V3h-6z"/>
      </svg>
    ),
  },
  {
    name: 'FFmpeg',
    description: 'Audio assembly, chapter embedding, M4B muxing, and two-pass loudness normalization.',
    version: '6.x',
    color: 'from-green-500/20 to-emerald-500/10',
    border: 'border-green-500/20',
    textColor: 'text-green-400',
    icon: (
      <svg viewBox="0 0 24 24" className="w-8 h-8 fill-current">
        <path d="M4 6H2v14c0 1.1.9 2 2 2h14v-2H4V6zm16-4H8c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm-8 12.5v-9l6 4.5-6 4.5z"/>
      </svg>
    ),
  },
  {
    name: 'Gradio',
    description: 'Zero-config browser UI. Drop files, configure voices, and monitor generation in real time.',
    version: '4.x',
    color: 'from-orange-500/20 to-amber-500/10',
    border: 'border-orange-500/20',
    textColor: 'text-orange-400',
    icon: (
      <svg viewBox="0 0 24 24" className="w-8 h-8 fill-current">
        <path d="M3 13h8V3H3v10zm0 8h8v-6H3v6zm10 0h8V11h-8v10zm0-18v6h8V3h-8z"/>
      </svg>
    ),
  },
  {
    name: 'spaCy',
    description: 'Industrial-strength NLP for named entity recognition — identifies character names in prose.',
    version: '3.x',
    color: 'from-violet-500/20 to-purple-500/10',
    border: 'border-violet-500/20',
    textColor: 'text-violet-400',
    icon: (
      <svg viewBox="0 0 24 24" className="w-8 h-8 fill-current">
        <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/>
      </svg>
    ),
  },
];

const containerVariants = {
  hidden: {},
  visible: {
    transition: { staggerChildren: 0.08 },
  },
};

const itemVariants = {
  hidden: { opacity: 0, scale: 0.9, y: 20 },
  visible: {
    opacity: 1,
    scale: 1,
    y: 0,
    transition: { duration: 0.5, ease: [0.25, 0.46, 0.45, 0.94] },
  },
};

export default function TechStack() {
  const ref = useRef(null);
  const isInView = useInView(ref, { once: true, margin: '-80px' });

  return (
    <section id="tech" className="relative py-28 px-6" ref={ref}>
      {/* Background accent */}
      <div className="absolute inset-0 -z-10">
        <div className="absolute inset-0 bg-gradient-to-b from-transparent via-indigo-950/10 to-transparent" />
        <div className="absolute inset-0 bg-grid-pattern opacity-30" />
      </div>

      <div className="max-w-6xl mx-auto">
        {/* Header */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={isInView ? { opacity: 1, y: 0 } : {}}
          transition={{ duration: 0.6 }}
          className="text-center mb-16"
        >
          <span className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-violet-600/10 border border-violet-500/20 text-violet-300 text-xs font-medium uppercase tracking-widest mb-4">
            Built on proven tools
          </span>
          <h2 className="text-4xl md:text-5xl font-black text-white leading-tight">
            Best-in-class{' '}
            <span className="gradient-text">tech stack</span>
          </h2>
          <p className="mt-4 text-slate-400 text-lg max-w-xl mx-auto">
            Assembled from battle-tested open-source libraries — no reinventing the wheel.
          </p>
        </motion.div>

        {/* Tech grid */}
        <motion.div
          variants={containerVariants}
          initial="hidden"
          animate={isInView ? 'visible' : 'hidden'}
          className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5"
        >
          {technologies.map((tech) => (
            <motion.div
              key={tech.name}
              variants={itemVariants}
              className={`group relative rounded-2xl p-6 bg-gradient-to-br ${tech.color} border ${tech.border} hover:scale-[1.02] transition-all duration-300 cursor-default overflow-hidden`}
            >
              {/* Top row */}
              <div className="flex items-start justify-between mb-4">
                <div className={`${tech.textColor} opacity-80 group-hover:opacity-100 transition-opacity`}>
                  {tech.icon}
                </div>
                <span className={`text-xs px-2 py-0.5 rounded-full border ${tech.border} ${tech.textColor} font-mono font-medium bg-black/20`}>
                  {tech.version}
                </span>
              </div>

              <h3 className={`text-xl font-black ${tech.textColor} mb-2`}>{tech.name}</h3>
              <p className="text-sm text-slate-400 leading-relaxed">{tech.description}</p>

              {/* Corner accent */}
              <div className={`absolute -bottom-4 -right-4 w-20 h-20 rounded-full ${tech.textColor} opacity-5 group-hover:opacity-10 transition-opacity blur-xl`} />
            </motion.div>
          ))}
        </motion.div>

        {/* Requirements callout */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={isInView ? { opacity: 1, y: 0 } : {}}
          transition={{ duration: 0.6, delay: 0.5 }}
          className="mt-12 rounded-2xl border border-white/8 bg-[#0d1117] overflow-hidden"
        >
          <div className="px-6 py-4 border-b border-white/5 bg-[#161b22] flex items-center gap-3">
            <div className="flex gap-1.5">
              <div className="w-3 h-3 rounded-full bg-red-500/70" />
              <div className="w-3 h-3 rounded-full bg-yellow-500/70" />
              <div className="w-3 h-3 rounded-full bg-green-500/70" />
            </div>
            <span className="text-sm text-slate-400 font-mono">install.sh</span>
          </div>
          <div className="p-6 font-mono text-sm space-y-2 overflow-x-auto">
            <div>
              <span className="text-slate-500"># Clone & install</span>
            </div>
            <div>
              <span className="text-violet-400">git</span>
              <span className="text-slate-300"> clone https://github.com/your-repo/audiobook-creator-v7</span>
            </div>
            <div>
              <span className="text-violet-400">cd</span>
              <span className="text-slate-300"> audiobook-creator-v7</span>
            </div>
            <div>
              <span className="text-violet-400">pip</span>
              <span className="text-slate-300"> install -r requirements.txt</span>
            </div>
            <div className="pt-1">
              <span className="text-slate-500"># Launch the UI</span>
            </div>
            <div>
              <span className="text-violet-400">python</span>
              <span className="text-slate-300"> src_ui.py</span>
            </div>
            <div className="pt-1">
              <span className="text-slate-500"># Open http://localhost:7860</span>
            </div>
          </div>
        </motion.div>
      </div>
    </section>
  );
}
