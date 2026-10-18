import type { Metadata } from 'next';
import localFont from 'next/font/local';
import './globals.css';

// Fonts ship with the repo (SIL Open Font License, files from Fontsource): the image build
// never downloads them, so it cannot fail on a flaky Google Fonts response. Japanese text
// uses the system font (Hiragino, Yu Gothic, Noto), as it did before.
const barlow = localFont({
  variable: '--font-barlow',
  src: [
    { path: './fonts/barlow-condensed-latin-600-normal.woff2', weight: '600' },
    { path: './fonts/barlow-condensed-latin-700-normal.woff2', weight: '700' },
  ],
});
const plexSans = localFont({
  variable: '--font-plex-sans',
  src: [
    { path: './fonts/ibm-plex-sans-latin-400-normal.woff2', weight: '400' },
    { path: './fonts/ibm-plex-sans-latin-500-normal.woff2', weight: '500' },
    { path: './fonts/ibm-plex-sans-latin-600-normal.woff2', weight: '600' },
  ],
});
const plexMono = localFont({
  variable: '--font-plex-mono',
  src: [{ path: './fonts/ibm-plex-mono-latin-500-normal.woff2', weight: '500' }],
});

export const metadata: Metadata = {
  title: 'Formline Live Viewer',
  description: 'Live football insight engine: explainable, personalized match overlays.',
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={`${barlow.variable} ${plexSans.variable} ${plexMono.variable}`}>
      <body>{children}</body>
    </html>
  );
}
