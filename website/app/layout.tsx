import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'Audiobook Creator V7 — Your Books. Your Voice.',
  description:
    'Convert any EPUB, PDF, TXT, or web article into a fully-chaptered M4B audiobook with per-character neural voices. Free, open source, runs locally.',
  keywords: [
    'audiobook',
    'epub to audiobook',
    'text to speech',
    'tts',
    'edge-tts',
    'kokoro',
    'open source',
    'm4b',
    'neural voices',
  ],
  openGraph: {
    title: 'Audiobook Creator V7 — Your Books. Your Voice.',
    description:
      'Convert any book into a chaptered M4B audiobook with per-character neural voices — free, open source, runs locally.',
    type: 'website',
  },
  twitter: {
    card: 'summary_large_image',
    title: 'Audiobook Creator V7 — Your Books. Your Voice.',
    description:
      'Convert any book into a chaptered M4B audiobook with per-character neural voices — free, open source, runs locally.',
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body className="bg-navy-950 text-slate-100 antialiased">{children}</body>
    </html>
  );
}
