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
  icons: {
    icon: [
      { url: "/favicon.svg", type: "image/svg+xml" },
      { url: "/favicon-32.png", sizes: "32x32", type: "image/png" },
      { url: "/favicon-16.png", sizes: "16x16", type: "image/png" },
    ],
    shortcut: "/favicon.ico",
    apple: "/apple-touch-icon.png",
  },
  manifest: "/site.webmanifest",
  openGraph: {
    title: "Afefehub",
    description: "Real reviews from real faces. Find businesses across Africa reviewed on video.",
    siteName: "Afefehub",
    type: "website",
    images: [{ url: "/og-image.png", width: 1200, height: 630, alt: "Afefehub — real reviews from real faces" }],
  },
  twitter: {
    card: "summary_large_image",
    title: "Afefehub",
    description: "Real reviews from real faces. Find businesses across Africa reviewed on video.",
    images: ["/og-image.png"],
  },
};

export const viewport: Viewport = {
  themeColor: "#ffc72c",
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
