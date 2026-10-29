import type { Metadata, Viewport } from "next";
import { Fraunces, Inter } from "next/font/google";
import "./globals.css";
import Header from "@/components/Header";
import Footer from "@/components/Footer";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter", display: "swap" });
const fraunces = Fraunces({ subsets: ["latin"], variable: "--font-fraunces", display: "swap", axes: ["opsz"] });

export const metadata: Metadata = {
  title: { default: "Afefehub — real reviews from real faces", template: "%s · Afefehub" },
  description:
    "Find businesses across Africa reviewed on video. Authentic Instagram reel reviews, verified and summarised by AI.",
  metadataBase: new URL("https://afefehub.com"),
  icons: { icon: "/favicon.svg" },
  openGraph: {
    title: "Afefehub",
    description: "Real reviews from real faces. Find businesses across Africa reviewed on video.",
    siteName: "Afefehub",
    type: "website",
  },
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#fdf9f2" },
    { media: "(prefers-color-scheme: dark)", color: "#14121a" },
  ],
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${inter.variable} ${fraunces.variable}`}>
      <body className="flex min-h-dvh flex-col">
        <Header />
        <main className="mx-auto w-full max-w-5xl flex-1 px-4 pb-16 sm:px-6">{children}</main>
        <Footer />
      </body>
    </html>
  );
}
