export function CTA() {
  return (
    <section className="border-t border-slate-800 px-6 py-20">
      <div className="mx-auto max-w-2xl rounded-2xl border border-sky-500/30 bg-sky-500/5 px-8 py-12 text-center">
        <h2 className="text-xl font-bold sm:text-2xl">
          Ready to Create Your Audiobook?
        </h2>
        <p className="mt-4 text-slate-400">
          Clone the repo, install dependencies, and run. Or try it on Hugging
          Face Spaces.
        </p>
        <div className="mt-8 flex flex-wrap justify-center gap-4">
          <a
            href="https://github.com"
            target="_blank"
            rel="noopener noreferrer"
            className="rounded-lg bg-sky-500 px-6 py-3 font-medium text-white transition hover:bg-sky-600"
          >
            Get Started on GitHub
          </a>
          <a
            href="https://huggingface.co/spaces"
            target="_blank"
            rel="noopener noreferrer"
            className="rounded-lg border border-slate-600 px-6 py-3 font-medium transition hover:border-sky-500 hover:text-sky-400"
          >
            Try on Hugging Face
          </a>
        </div>
        <p className="mt-6 text-sm text-slate-500">
          <code className="rounded bg-slate-800 px-2 py-1">
            pip install -r requirements.txt && python app.py
          </code>
        </p>
      </div>
    </section>
  );
}
