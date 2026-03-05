const features = [
  {
    title: 'EPUB, PDF & TXT',
    description: 'Drop any book format. Supports URLs and pasted text too.',
    icon: '📖',
  },
  {
    title: 'Neural TTS',
    description: 'Edge-TTS (cloud) or Kokoro (offline). 7+ voices, character attribution.',
    icon: '🎤',
  },
  {
    title: 'Smart Chapters',
    description: 'Auto-detect chapters from TOC, headings, or font size. M4B chapter markers.',
    icon: '📑',
  },
  {
    title: 'Character Voices',
    description: 'Regex + spaCy detect dialogue. Assign unique voices per character.',
    icon: '🎭',
  },
  {
    title: 'Resume & Cache',
    description: 'Manifest-based pipeline. Stop and resume. Reuse cached segments.',
    icon: '⚡',
  },
  {
    title: 'Low-Spec Friendly',
    description: 'Runs on 2 cores, 3.4GB RAM. Generator-based streaming, no full-book load.',
    icon: '💻',
  },
];

export function Features() {
  return (
    <section className="border-t border-slate-800 px-6 py-20">
      <div className="mx-auto max-w-6xl">
        <h2 className="text-center text-2xl font-bold sm:text-3xl">
          Everything You Need
        </h2>
        <p className="mx-auto mt-4 max-w-2xl text-center text-slate-400">
          A complete pipeline from text to audiobook, designed for long books and
          low-spec machines.
        </p>
        <div className="mt-16 grid gap-8 sm:grid-cols-2 lg:grid-cols-3">
          {features.map((f) => (
            <div
              key={f.title}
              className="rounded-xl border border-slate-800 bg-slate-900/50 p-6 transition hover:border-sky-500/50"
            >
              <span className="text-3xl">{f.icon}</span>
              <h3 className="mt-4 font-semibold">{f.title}</h3>
              <p className="mt-2 text-sm text-slate-400">{f.description}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
