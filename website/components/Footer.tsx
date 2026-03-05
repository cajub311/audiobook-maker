'use client';

import { motion } from 'framer-motion';
import { useInView } from 'framer-motion';
import { useRef } from 'react';

const GITHUB_URL = 'https://github.com';

const navLinks = [
  { label: 'Features', href: '#features' },
  { label: 'How It Works', href: '#how-it-works' },
  { label: 'Tech Stack', href: '#tech' },
];

const resourceLinks = [
  { label: 'GitHub Repository', href: GITHUB_URL },
  { label: 'MIT License', href: `${GITHUB_URL}/blob/main/LICENSE` },
  { label: 'Issues & Bug Reports', href: `${GITHUB_URL}/issues` },
  { label: 'Discussions', href: `${GITHUB_URL}/discussions` },
];

export default function Footer() {
  const ref = useRef(null);
  const isInView = useInView(ref, { once: true, margin: '-80px' });

  return (
    <footer className="relative pt-20 pb-10 px-6" ref={ref}>
      {/* Top gradient separator */}
      <div className="absolute top-0 left-0 right-0 h-px bg-gradient-to-r from-transparent via-violet-500/30 to-transparent" />

      {/* CTA Banner */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={isInView ? { opacity: 1, y: 0 } : {}}
        transition={{ duration: 0.6 }}
        className="max-w-4xl mx-auto mb-20"
      >
        <div className="relative rounded-3xl overflow-hidden border border-violet-500/20 bg-gradient-to-br from-violet-600/15 via-violet-900/10 to-transparent p-10 md:p-14 text-center">
          {/* Ambient glow */}
          <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[300px] h-[200px] bg-violet-600/20 blur-[80px] -z-10" />

          <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-violet-600/15 border border-violet-500/20 text-violet-300 text-xs font-medium uppercase tracking-widest mb-6">
            <svg className="w-3 h-3 fill-current" viewBox="0 0 20 20">
              <path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z" />
            </svg>
            Free & Open Source
          </div>

          <h2 className="text-4xl md:text-5xl font-black text-white mb-4 leading-tight">
            Start listening to{' '}
            <span className="gradient-text">your books</span>
            <br className="hidden md:block" /> today
          </h2>

          <p className="text-slate-400 text-lg mb-8 max-w-xl mx-auto">
            No subscriptions. No API keys for offline mode. No limits. Just great audiobooks from your own library.
          </p>

          <div className="flex flex-col sm:flex-row gap-4 justify-center">
            <a
              href={GITHUB_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center justify-center gap-2.5 px-8 py-3.5 rounded-xl bg-violet-600 hover:bg-violet-500 text-white font-semibold text-base transition-all duration-200 shadow-lg shadow-violet-600/30 hover:shadow-violet-500/40 hover:scale-105"
            >
              <GitHubIcon />
              View on GitHub
            </a>
            <a
              href={`${GITHUB_URL}/releases`}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center justify-center gap-2 px-8 py-3.5 rounded-xl border border-white/10 bg-white/5 hover:bg-white/10 text-white font-semibold text-base transition-all duration-200 hover:scale-105"
            >
              Download Latest
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
              </svg>
            </a>
          </div>
        </div>
      </motion.div>

      {/* Footer content */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={isInView ? { opacity: 1, y: 0 } : {}}
        transition={{ duration: 0.6, delay: 0.2 }}
        className="max-w-6xl mx-auto"
      >
        <div className="grid grid-cols-1 md:grid-cols-3 gap-10 pb-10 border-b border-white/5">
          {/* Brand */}
          <div className="space-y-4">
            <div className="flex items-center gap-2.5">
              <div className="w-8 h-8 rounded-lg bg-violet-600 flex items-center justify-center flex-shrink-0">
                <svg className="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19V6l12-3v13M9 19c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zm12-3c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zM9 10l12-3" />
                </svg>
              </div>
              <span className="font-bold text-white">Audiobook Creator V7</span>
            </div>
            <p className="text-sm text-slate-500 leading-relaxed">
              Convert EPUB, PDF, TXT, and web articles into fully-chaptered M4B audiobooks with per-character neural voices.
            </p>
            <div className="flex items-center gap-2 flex-wrap">
              <span className="px-2 py-0.5 rounded bg-white/5 border border-white/8 text-xs text-slate-400 font-mono">MIT License</span>
              <span className="px-2 py-0.5 rounded bg-white/5 border border-white/8 text-xs text-slate-400 font-mono">Python 3.10+</span>
              <span className="px-2 py-0.5 rounded bg-white/5 border border-white/8 text-xs text-slate-400 font-mono">v7.0</span>
            </div>
          </div>

          {/* Navigation */}
          <div>
            <h4 className="text-sm font-semibold text-white uppercase tracking-widest mb-4">Navigation</h4>
            <ul className="space-y-2.5">
              {navLinks.map(({ label, href }) => (
                <li key={label}>
                  <a href={href} className="text-sm text-slate-400 hover:text-violet-400 transition-colors flex items-center gap-1.5 group">
                    <span className="w-1 h-1 rounded-full bg-violet-500/0 group-hover:bg-violet-500 transition-all" />
                    {label}
                  </a>
                </li>
              ))}
            </ul>
          </div>

          {/* Resources */}
          <div>
            <h4 className="text-sm font-semibold text-white uppercase tracking-widest mb-4">Resources</h4>
            <ul className="space-y-2.5">
              {resourceLinks.map(({ label, href }) => (
                <li key={label}>
                  <a
                    href={href}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-sm text-slate-400 hover:text-violet-400 transition-colors flex items-center gap-1.5 group"
                  >
                    <span className="w-1 h-1 rounded-full bg-violet-500/0 group-hover:bg-violet-500 transition-all" />
                    {label}
                    <svg className="w-3 h-3 opacity-0 group-hover:opacity-100 transition-opacity" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                    </svg>
                  </a>
                </li>
              ))}
            </ul>
          </div>
        </div>

        {/* Bottom bar */}
        <div className="pt-8 flex flex-col md:flex-row items-center justify-between gap-4">
          <p className="text-sm text-slate-600">
            Released under the{' '}
            <a href={`${GITHUB_URL}/blob/main/LICENSE`} target="_blank" rel="noopener noreferrer" className="text-slate-500 hover:text-violet-400 transition-colors underline underline-offset-2">
              MIT License
            </a>
            . Made with care for the audiobook community.
          </p>

          <div className="flex items-center gap-3">
            <a
              href={GITHUB_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="w-8 h-8 rounded-lg bg-white/5 border border-white/8 hover:bg-white/10 flex items-center justify-center text-slate-400 hover:text-white transition-all"
              aria-label="GitHub"
            >
              <GitHubIcon />
            </a>
            <span className="text-xs text-slate-600 font-mono">Audiobook Creator V7</span>
          </div>
        </div>
      </motion.div>
    </footer>
  );
}

function GitHubIcon() {
  return (
    <svg className="w-4 h-4 fill-current" viewBox="0 0 24 24">
      <path d="M12 0C5.374 0 0 5.373 0 12c0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23A11.509 11.509 0 0112 5.803c1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576C20.566 21.797 24 17.3 24 12c0-6.627-5.373-12-12-12z" />
    </svg>
  );
}
