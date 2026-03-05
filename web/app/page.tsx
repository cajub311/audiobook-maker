import { Hero } from '../components/Hero';
import { Features } from '../components/Features';
import { HowItWorks } from '../components/HowItWorks';
import { CTA } from '../components/CTA';

export default function Home() {
  return (
    <main>
      <Hero />
      <Features />
      <HowItWorks />
      <CTA />
      <footer className="border-t border-slate-800 py-8 text-center text-sm text-slate-500">
        Audiobook Creator V7 — Open source • Built with Gradio & FFmpeg
      </footer>
    </main>
  );
}
