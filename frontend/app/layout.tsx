import type { Metadata, Viewport } from "next";
import { Lato } from "next/font/google";
import "./globals.css";
import Header from "@/components/Header";
import Footer from "@/components/Footer";

const lato = Lato({ subsets: ["latin"], weight: ["400", "700", "900"], variable: "--font-lato", display: "swap" });

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
    { media: "(prefers-color-scheme: light)", color: "#ffffff" },
    { media: "(prefers-color-scheme: dark)", color: "#050d24" },
  ],
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={lato.variable}>
      <body className="flex min-h-dvh flex-col">
        <Header />
        <main className="mx-auto w-full max-w-5xl flex-1 px-4 pb-16 sm:px-6">{children}</main>
        <Footer />
      </body>
    </html>
  );
}
