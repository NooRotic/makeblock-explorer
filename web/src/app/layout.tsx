import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import Link from "next/link";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "MakeBlock Explorer",
  description: "MakeBlock CyberPi device dashboard",
};

const navLinks = [
  { href: "/", label: "Dashboard" },
  { href: "/controls", label: "Controls" },
  { href: "/notify", label: "Notify" },
  { href: "/settings", label: "Settings" },
];

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} dark h-full antialiased`}
    >
      <body className="min-h-full flex flex-col bg-gray-950 text-gray-100">
        <nav className="bg-gray-900 border-b border-gray-800 px-6 py-3">
          <div className="max-w-5xl mx-auto flex items-center gap-6">
            <span className="text-sm font-bold text-gray-300 mr-2">
              MakeBlock Explorer
            </span>
            {navLinks.map(({ href, label }) => (
              <Link
                key={href}
                href={href}
                className="text-sm text-gray-400 hover:text-gray-100 transition-colors"
              >
                {label}
              </Link>
            ))}
          </div>
        </nav>
        <main className="flex-1 max-w-5xl mx-auto w-full px-6 py-8">
          {children}
        </main>
      </body>
    </html>
  );
}
