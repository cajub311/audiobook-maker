'use client';

import { motion } from 'framer-motion';

const GITHUB_URL = 'https://github.com';

const fadeUp = {
  hidden: { opacity: 0, y: 30 },
  visible: (delay: number) => ({
    opacity: 1,
    y: 0,
    transition: { duration: 0.7, delay, ease: [0.25, 0.46, 0.45, 0.94] },
  }),
};

function GradioMockup() {
  return (
    <div className="relative w-full max-w-2xl mx-auto">
      {/* Glow behind window */}
      <div className="absolute inset-0 bg-violet-600/20 blur-3xl rounded-3xl scale-95 -z-10" />

      {/* Browser chrome */}
      <div className="rounded-2xl overflow-hidden border border-white/10 shadow-2xl bg-[#0d1117]">
        {/* Title bar */}
        <div className="flex items-center gap-2 px-4 py-3 bg-[#161b22] border-b border-white/5">
          <div className="flex gap-1.5">
            <div className="w-3 h-3 rounded-full bg-red-500/80" />
            <div className="w-3 h-3 rounded-full bg-yellow-500/80" />
            <div className="w-3 h-3 rounded-full bg-green-500/80" />
          </div>
          <div className="flex-1 flex justify-center">
            <div className="flex items-center gap-2 bg-[#0d1117] rounded-md px-3 py-1 text-xs text-slate-400 font-mono border border-white/5">
              <svg className="w-3 h-3 text-green-400" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M5 9V7a5 5 0 0110 0v2a2 2 0 012 2v5a2 2 0 01-2 2H5a2 2 0 01-2-2v-5a2 2 0 012-2zm8-2v2H7V7a3 3 0 016 0z" clipRule="evenodd" />
              </svg>
              localhost:7860
            </div>
          </div>
        </div>

        {/* App header */}
        <div className="bg-gradient-to-r from-[#0d1117] via-[#13192a] to-[#0d1117] px-6 pt-5 pb-4 border-b border-white/5">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-violet-600 flex items-center justify-center">
              <svg className="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19V6l12-3v13M9 19c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zm12-3c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zM9 10l12-3" />
              </svg>
            </div>
            <div>
              <h3 className="text-sm font-semibold text-white">Audiobook Creator V7</h3>
              <p className="text-xs text-slate-400">EPUB / PDF / TXT → M4B</p>
            </div>
          </div>
        </div>

        {/* Tabs */}
        <div className="flex border-b border-white/5 bg-[#0d1117]">
          {['📚 Input', '🎙️ Voices', '⚙️ Settings', '▶ Generate'].map((tab, i) => (
            <button
              key={tab}
              className={`px-4 py-2.5 text-xs font-medium transition-colors ${
                i === 0
                  ? 'text-violet-400 border-b-2 border-violet-500 bg-violet-500/5'
                  : 'text-slate-500 hover:text-slate-300'
              }`}
            >
              {tab}
            </button>
          ))}
        </div>

        {/* Content area */}
        <div className="p-5 space-y-4 bg-[#0d1117]">
          {/* Upload zone */}
          <div className="border-2 border-dashed border-violet-500/30 rounded-xl p-6 text-center bg-violet-500/5 hover:border-violet-500/50 transition-colors cursor-pointer group">
            <div className="w-10 h-10 mx-auto mb-3 rounded-xl bg-violet-600/20 flex items-center justify-center group-hover:bg-violet-600/30 transition-colors">
              <svg className="w-5 h-5 text-violet-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
              </svg>
            </div>
            <p className="text-sm text-slate-300 font-medium">Drop your EPUB, PDF, or TXT</p>
            <p className="text-xs text-slate-500 mt-1">or paste a URL below</p>
          </div>

          {/* URL input */}
          <div className="flex gap-2">
            <div className="flex-1 bg-[#161b22] border border-white/8 rounded-lg px-3 py-2 text-xs text-slate-400 font-mono flex items-center gap-2">
              <span className="text-violet-400">https://</span>
              <span className="text-slate-500">www.gutenberg.org/ebooks/...</span>
            </div>
            <button className="px-3 py-2 bg-violet-600 hover:bg-violet-500 rounded-lg text-xs text-white font-medium transition-colors">
              Fetch
            </button>
          </div>

          {/* Progress bar */}
          <div className="space-y-1.5">
            <div className="flex justify-between text-xs">
              <span className="text-slate-400">Generating Chapter 3 / 12</span>
              <span className="text-violet-400 font-medium">41%</span>
            </div>
            <div className="h-1.5 bg-[#161b22] rounded-full overflow-hidden">
              <div
                className="h-full bg-gradient-to-r from-violet-600 to-purple-500 rounded-full"
                style={{ width: '41%' }}
              />
            </div>
            <div className="flex gap-1 flex-wrap">
              {Array.from({ length: 12 }, (_, i) => (
                <div
                  key={i}
                  className={`h-1 flex-1 rounded-full ${
                    i < 4 ? 'bg-violet-500' : i === 4 ? 'bg-violet-500/50 animate-pulse' : 'bg-white/5'
                  }`}
                />
              ))}
            </div>
          </div>

          {/* Status line */}
          <div className="flex items-center gap-2 text-xs text-slate-400 font-mono bg-[#161b22] rounded-lg px-3 py-2">
            <span className="w-1.5 h-1.5 rounded-full bg-green-400 animate-pulse flex-shrink-0" />
            Synthesizing "Arlen" → en-GB-RyanNeural · segment 7/23
          </div>
        </div>
      </div>
    </div>
  );
}

export default function Hero() {
  return (
    <section className="relative min-h-screen flex flex-col items-center justify-center px-6 pt-24 pb-16">
      {/* Navigation */}
      <motion.nav
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5 }}
        className="fixed top-0 left-0 right-0 z-50 flex items-center justify-between px-6 py-4 glass border-b border-white/5"
      >
        <div className="flex items-center gap-2.5">
          <div className="w-7 h-7 rounded-lg bg-violet-600 flex items-center justify-center">
            <svg className="w-4 h-4 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19V6l12-3v13M9 19c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zm12-3c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zM9 10l12-3" />
            </svg>
          </div>
          <span className="font-semibold text-white text-sm">Audiobook Creator V7</span>
        </div>
        <div className="hidden md:flex items-center gap-6 text-sm text-slate-400">
          <a href="#features" className="hover:text-white transition-colors">Features</a>
          <a href="#how-it-works" className="hover:text-white transition-colors">How It Works</a>
          <a href="#tech" className="hover:text-white transition-colors">Tech Stack</a>
          <a
            href={GITHUB_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white/5 hover:bg-white/10 text-white border border-white/10 transition-all"
          >
            <GitHubIcon />
            GitHub
          </a>
        </div>
      </motion.nav>

      {/* Badge */}
      <motion.div
        custom={0}
        initial="hidden"
        animate="visible"
        variants={fadeUp}
        className="mb-8"
      >
        <span className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-violet-600/10 border border-violet-500/20 text-violet-300 text-sm font-medium">
          <span className="w-2 h-2 rounded-full bg-violet-400 animate-pulse" />
          Open Source · MIT License · Free Forever
        </span>
      </motion.div>

      {/* Headline */}
      <motion.h1
        custom={0.1}
        initial="hidden"
        animate="visible"
        variants={fadeUp}
        className="text-5xl md:text-7xl lg:text-8xl font-black text-center text-balance leading-[1.05] tracking-tight max-w-5xl"
      >
        Your Books.{' '}
        <span className="gradient-text-light">Your Voice.</span>
      </motion.h1>

      {/* Sub-headline */}
      <motion.p
        custom={0.2}
        initial="hidden"
        animate="visible"
        variants={fadeUp}
        className="mt-6 text-lg md:text-xl text-slate-400 text-center text-balance max-w-2xl leading-relaxed"
      >
        Convert any book into a chaptered M4B audiobook with{' '}
        <span className="text-violet-300 font-medium">per-character neural voices</span> — free,
        open source, runs locally.
      </motion.p>

      {/* CTA buttons */}
      <motion.div
        custom={0.3}
        initial="hidden"
        animate="visible"
        variants={fadeUp}
        className="mt-10 flex flex-col sm:flex-row gap-4"
      >
        <a
          href={GITHUB_URL}
          target="_blank"
          rel="noopener noreferrer"
          className="group flex items-center justify-center gap-2.5 px-7 py-3.5 rounded-xl bg-violet-600 hover:bg-violet-500 text-white font-semibold text-base transition-all duration-200 shadow-lg shadow-violet-600/30 hover:shadow-violet-500/40 hover:scale-105"
        >
          <svg className="w-5 h-5 fill-current" viewBox="0 0 20 20">
            <path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z" />
          </svg>
          Star on GitHub
        </a>
        <a
          href="#how-it-works"
          className="flex items-center justify-center gap-2 px-7 py-3.5 rounded-xl border border-white/10 bg-white/5 hover:bg-white/10 text-white font-semibold text-base transition-all duration-200 hover:scale-105"
        >
          Read the Docs
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 8l4 4m0 0l-4 4m4-4H3" />
          </svg>
        </a>
      </motion.div>

      {/* Stats row */}
      <motion.div
        custom={0.4}
        initial="hidden"
        animate="visible"
        variants={fadeUp}
        className="mt-12 flex flex-wrap justify-center gap-8 text-center"
      >
        {[
          { value: '4', label: 'Input Formats' },
          { value: '∞', label: 'Neural Voices' },
          { value: '0', label: 'Cost' },
          { value: '100%', label: 'Local & Private' },
        ].map(({ value, label }) => (
          <div key={label} className="flex flex-col items-center gap-1">
            <span className="text-3xl font-black gradient-text">{value}</span>
            <span className="text-xs text-slate-500 uppercase tracking-widest font-medium">{label}</span>
          </div>
        ))}
      </motion.div>

      {/* Browser mockup */}
      <motion.div
        custom={0.5}
        initial="hidden"
        animate="visible"
        variants={fadeUp}
        className="mt-16 w-full max-w-2xl"
      >
        <GradioMockup />
      </motion.div>

      {/* Scroll indicator */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 1.2, duration: 0.5 }}
        className="mt-16 flex flex-col items-center gap-2 text-slate-600"
      >
        <span className="text-xs uppercase tracking-widest">Scroll to explore</span>
        <div className="w-px h-8 bg-gradient-to-b from-violet-500/50 to-transparent" />
      </motion.div>
    </section>
  );
}

function GitHubIcon() {
  return (
    <svg className="w-4 h-4 fill-current" viewBox="0 0 24 24">
      <path d="M12 0C5.374 0 0 5.373 0 12c0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23A11.509 11.509 0 0112 5.803c1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576C20.566 21.797 24 17.3 24 12c0-6.627-5.373-12-12-12z" />
    </svg>
  );
}
