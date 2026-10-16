import type { Metadata } from 'next';
import { Barlow_Condensed, IBM_Plex_Mono, IBM_Plex_Sans, Noto_Sans_JP } from 'next/font/google';
import './globals.css';

const barlow = Barlow_Condensed({ variable: '--font-barlow', weight: ['600', '700'], subsets: ['latin'] });
const plexSans = IBM_Plex_Sans({ variable: '--font-plex-sans', weight: ['400', '500', '600'], subsets: ['latin'] });
const plexMono = IBM_Plex_Mono({ variable: '--font-plex-mono', weight: ['500'], subsets: ['latin'] });
const notoJp = Noto_Sans_JP({ variable: '--font-noto-jp', weight: ['400', '700'], subsets: ['latin'], preload: false });

export const metadata: Metadata = {
  title: 'Formline Live Viewer',
  description: 'Live football insight engine: explainable, personalized match overlays.',
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={`${barlow.variable} ${plexSans.variable} ${plexMono.variable} ${notoJp.variable}`}>
      <body>{children}</body>
    </html>
  );
}
