export function Hero() {
  return (
    <section className="relative overflow-hidden px-6 py-24 sm:py-32">
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_80%_50%_at_50%_-20%,rgba(14,165,233,0.15),transparent)]" />
      <div className="relative mx-auto max-w-4xl text-center">
        <h1 className="text-4xl font-bold tracking-tight sm:text-6xl">
          Turn Any Book Into an{' '}
          <span className="gradient-text">Audiobook</span>
        </h1>
        <p className="mt-6 text-lg text-slate-400 sm:text-xl">
          Convert EPUB, PDF, or TXT to professional audiobooks with neural TTS,
          character voices, and smart chapter detection. Free, open source, runs
          locally or in the cloud.
        </p>
        <div className="mt-10 flex flex-wrap justify-center gap-4">
          <a
            href="https://github.com"
            target="_blank"
            rel="noopener noreferrer"
            className="rounded-lg bg-sky-500 px-6 py-3 font-medium text-white transition hover:bg-sky-600"
          >
            View on GitHub
          </a>
          <a
            href="#how-it-works"
            className="rounded-lg border border-slate-600 px-6 py-3 font-medium transition hover:border-sky-500 hover:text-sky-400"
          >
            How It Works
          </a>
        </div>
      </div>
    </section>
  );
}
