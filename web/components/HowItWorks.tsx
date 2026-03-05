const steps = [
  {
    step: 1,
    title: 'Parse',
    description:
      'Extract text chapter by chapter. Detect chapters, dialogue, speakers, scene breaks. Build manifest.',
  },
  {
    step: 2,
    title: 'Generate',
    description:
      'TTS each segment in parallel. Apply pronunciation overrides. Cache results. Resume anytime.',
  },
  {
    step: 3,
    title: 'Assemble',
    description:
      'Concat with silence gaps. Normalize loudness (-19 LUFS). Embed chapters. Output M4B or MP3.',
  },
];

export function HowItWorks() {
  return (
    <section
      id="how-it-works"
      className="border-t border-slate-800 px-6 py-20"
    >
      <div className="mx-auto max-w-4xl">
        <h2 className="text-center text-2xl font-bold sm:text-3xl">
          How It Works
        </h2>
        <p className="mx-auto mt-4 max-w-2xl text-center text-slate-400">
          Three stages. One manifest. Full control.
        </p>
        <div className="mt-16 space-y-12">
          {steps.map((s) => (
            <div
              key={s.step}
              className="flex gap-6 rounded-xl border border-slate-800 bg-slate-900/30 p-6"
            >
              <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-sky-500/20 text-lg font-bold text-sky-400">
                {s.step}
              </div>
              <div>
                <h3 className="font-semibold">{s.title}</h3>
                <p className="mt-2 text-slate-400">{s.description}</p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
