import type { Metadata, Viewport } from "next";
import { headers } from "next/headers";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const viewport: Viewport = {
  themeColor: "#07100d",
  colorScheme: "dark",
};

export async function generateMetadata(): Promise<Metadata> {
  const requestHeaders = await headers();
  const host = requestHeaders.get("x-forwarded-host") ?? requestHeaders.get("host") ?? "localhost:3000";
  const protocol = requestHeaders.get("x-forwarded-proto") ?? (host.startsWith("localhost") ? "http" : "https");
  const metadataBase = new URL(`${protocol}://${host}`);

  return {
    metadataBase,
    title: "ChangeGuard — Live Gemini Multi-Agent Mission",
    description:
      "Six live Gemini agents investigate telecom incidents, expose structured reasoning logs, and produce one evidence-led response.",
    icons: { icon: "/favicon.svg", shortcut: "/favicon.svg" },
    openGraph: {
      title: "ChangeGuard — Live Gemini Multi-Agent Mission",
      description: "Six Gemini agents. Visible evidence. One agent-led response.",
      type: "website",
      images: [
        {
          url: "/og-ran-guardian.png",
          width: 1730,
          height: 909,
          alt: "ChangeGuard Gemini multi-agent telecom mission console",
        },
      ],
    },
    twitter: {
      card: "summary_large_image",
      title: "ChangeGuard — Live Gemini Multi-Agent Mission",
      description: "Six Gemini agents. Visible evidence. One agent-led response.",
      images: ["/og-ran-guardian.png"],
    },
  };
}

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body className={`${geistSans.variable} ${geistMono.variable}`}>{children}</body>
    </html>
  );
}
