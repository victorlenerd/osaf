import type { Metadata, Viewport } from "next";
import { Lato } from "next/font/google";
import "./globals.css";
import Header from "@/components/Header";
import Footer from "@/components/Footer";

const lato = Lato({ subsets: ["latin"], weight: ["400", "700", "900"], variable: "--font-lato", display: "swap" });

export const metadata: Metadata = {
  title: { default: "Afefehub — real reviews from real voices", template: "%s · Afefehub" },
  description:
    "Find businesses across Africa reviewed by real people. Authentic Instagram reel reviews and WhatsApp voice notes, verified and summarised by AI.",
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
  // Resolved per route, so each static page names itself as canonical.
  alternates: { canonical: "./" },
  openGraph: {
    title: "Afefehub",
    description: "Real reviews from real voices. Find businesses across Africa reviewed on video or by voice note.",
    siteName: "Afefehub",
    type: "website",
    images: [{ url: "/og-image.png", width: 1200, height: 630, alt: "Afefehub — real reviews from real voices" }],
  },
  twitter: {
    card: "summary_large_image",
    title: "Afefehub",
    description: "Real reviews from real voices. Find businesses across Africa reviewed on video or by voice note.",
    images: ["/og-image.png"],
  },
};

export const viewport: Viewport = {
  themeColor: "#ffc72c",
};

// Site-wide identity for search engines and AI assistants (business pages carry their own).
const SITE_JSONLD = {
  "@context": "https://schema.org",
  "@graph": [
    {
      "@type": "Organization",
      "@id": "https://afefehub.com/#org",
      name: "Afefehub",
      url: "https://afefehub.com/",
      logo: "https://afefehub.com/icon-512.png",
      description: "Authentic video and voice-note reviews of businesses across Africa, verified and summarised by AI.",
      parentOrganization: { "@type": "Organization", name: "1CTECH", url: "https://1ctech.ca" },
      sameAs: ["https://www.instagram.com/afefehub", "https://github.com/victorlenerd/osaf"],
    },
    {
      "@type": "WebSite",
      "@id": "https://afefehub.com/#website",
      name: "Afefehub",
      url: "https://afefehub.com/",
      publisher: { "@id": "https://afefehub.com/#org" },
    },
  ],
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={lato.variable}>
      <body className="flex min-h-dvh flex-col">
        <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(SITE_JSONLD) }} />
        <Header />
        <main className="mx-auto w-full max-w-5xl flex-1 px-4 pb-16 sm:px-6">{children}</main>
        <Footer />
      </body>
    </html>
  );
}
