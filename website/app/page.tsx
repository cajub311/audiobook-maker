import Hero from '@/components/Hero';
import Features from '@/components/Features';
import HowItWorks from '@/components/HowItWorks';
import VoiceDemo from '@/components/VoiceDemo';
import TechStack from '@/components/TechStack';
import Footer from '@/components/Footer';

export default function Home() {
  return (
    <main className="relative min-h-screen overflow-hidden">
      {/* Global ambient background */}
      <div className="fixed inset-0 -z-10">
        <div className="absolute inset-0 bg-[#020817]" />
        <div className="absolute top-0 left-1/4 w-[600px] h-[600px] bg-violet-600/10 rounded-full blur-[120px] -translate-y-1/2" />
        <div className="absolute top-1/3 right-0 w-[500px] h-[500px] bg-purple-800/8 rounded-full blur-[100px]" />
        <div className="absolute bottom-0 left-0 w-[400px] h-[400px] bg-indigo-900/10 rounded-full blur-[80px]" />
      </div>

      <Hero />
      <Features />
      <HowItWorks />
      <VoiceDemo />
      <TechStack />
      <Footer />
    </main>
  );
}
