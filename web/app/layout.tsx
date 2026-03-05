import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'Audiobook Creator V7 — Turn Any Book Into an Audiobook',
  description:
    'Convert EPUB, PDF, or TXT to professional audiobooks with neural TTS, character voices, and chapter detection.',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="scroll-smooth">
      <body className="min-h-screen bg-slate-950 text-slate-100 antialiased">
        {children}
      </body>
    </html>
  );
}
