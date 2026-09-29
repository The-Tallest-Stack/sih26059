import type { Metadata } from 'next';
import { Inter } from 'next/font/google';
import './globals.css';

const inter = Inter({ subsets: ['latin'] });

export const metadata: Metadata = {
  title: 'Antarctic DSS - Voyage Planning',
  description: 'AI-Enabled Antarctic Sea-Ice, Iceberg Trajectory, and Navigation Decision Support System',
};

import Link from 'next/link';

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className={`${inter.className} bg-gray-950 text-white h-screen overflow-hidden flex flex-col`}>
        <nav className="flex-shrink-0 border-b border-gray-800 bg-gray-900 px-4 py-2 flex gap-6 items-center">
          <Link href="/" className="font-bold text-xl tracking-tight text-blue-400">Antarctic DSS</Link>
          <Link href="/" className="hover:text-blue-300 transition-colors">Route Planner</Link>
          <Link href="/predictor" className="hover:text-blue-300 transition-colors">AI Trajectory Predictor</Link>
        </nav>
        {children}
      </body>
    </html>
  );
}
