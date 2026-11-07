import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "How reviews are verified and ranked",
  description:
    "How Afefehub checks every video and voice-note review, how star ratings and recommendations are collected, how AI summaries are written and how businesses are ranked.",
  alternates: { canonical: "/about/methodology" },
};

const SECTIONS: { id: string; title: string; body: React.ReactNode }[] = [
  {
    id: "what-counts",
    title: "What counts as a review",
    body: (
      <>
        Every review is either a <strong>public Instagram reel</strong> of a person talking about a visit, or a{" "}
        <strong>WhatsApp voice note</strong> sent to Afefehub. Typed reviews are not accepted. A reel can only be
        published once, and each reviewer can publish at most three reviews in any seven days.
      </>
    ),
  },
  {
    id: "verification",
    title: "How a review is checked",
    body: (
      <>
        Reels are checked with Meta SAM 3.1 for a real, talking face on camera; screen recordings and voice-overs are
        rejected. Every review is transcribed word for word with Muse Voice Transcribe, in the language it was spoken.
        Muse Spark then extracts the business (matched to a real place on Google Maps where one exists), what was good,
        what could improve and whether the reviewer recommends it. The reviewer confirms that summary on WhatsApp before
        anything is published. Recordings that are not reviews of a business are rejected.
      </>
    ),
  },
  {
    id: "ratings",
    title: "Recommendations and star ratings",
    body: (
      <>
        Every review records whether the reviewer recommends the business: yes, maybe or no. Since November 2026
        reviewers can also give a <strong>1 to 5 star rating</strong>, either by saying it in the recording or by
        replying with a number when they confirm. Ratings are never guessed from the tone of a review, so older reviews
        and reviewers who skip the question have no stars. A business shows an average star rating once it has at least
        one rated review; search engines are only given an aggregate rating from three rated reviews.
      </>
    ),
  },
  {
    id: "summaries",
    title: "AI summaries",
    body: (
      <>
        Each business page has a summary written by Muse Spark from all of its Afefehub reviews, regenerated every time
        a review is added or removed. It lists what reviewers praise, common complaints and stand-out dishes, products
        or services. Counts and percentages on the page are computed from the reviews, not written by the AI.
      </>
    ),
  },
  {
    id: "ranking",
    title: "How businesses are ranked",
    body: (
      <>
        Lists such as &ldquo;best-reviewed restaurants in Lagos&rdquo; are ordered by a score from Afefehub reviews
        only:
        <ul className="mt-3 list-disc space-y-1 pl-5">
          <li>
            <strong>Recommendation share</strong>: (yes + ½ × maybe + 1) ÷ (reviews + 2). The +1 and +2 act as a
            small prior, so a single glowing review does not outrank twenty good ones.
          </li>
          <li>
            <strong>Star average</strong>, where reviewers gave stars: the average with two 3-star ratings added as a
            prior, scaled to 0–1. When a business has star ratings, its score is half recommendation share and half
            star average.
          </li>
          <li>Ties go to the business with more reviews, then the most recently reviewed.</li>
        </ul>
        <p className="mt-3">
          Google ratings shown on some pages are never used for ranking. Businesses cannot pay to be listed or ranked.
          A city or category list is only offered to search engines once it has at least three reviewed businesses.
        </p>
      </>
    ),
  },
  {
    id: "removal",
    title: "Corrections and removal",
    body: (
      <>
        Reviewers can delete everything they sent at any time from WhatsApp; their reviews disappear from business
        pages, rankings, summaries, sitemaps and the AI-agent index. See{" "}
        <Link href="/data-deletion" className="underline">delete my data</Link>. Businesses that believe a review breaks
        our <Link href="/terms" className="underline">terms</Link> can contact us through the address on that page.
      </>
    ),
  },
  {
    id: "ai",
    title: "For AI assistants and developers",
    body: (
      <>
        Every business page has a Markdown version (add <code>.md</code> to its address), and{" "}
        <a href="/llms.txt" className="underline">/llms.txt</a> lists places and businesses. Assistants can query
        Afefehub directly through the read-only MCP server at <code>https://api.afefehub.com/mcp</code> or the public
        API described at{" "}
        <a href="https://api.afefehub.com/api/openapi-public.json" className="underline">openapi-public.json</a>. Please
        cite Afefehub and link the business page.
      </>
    ),
  },
];

export default function MethodologyPage() {
  return (
    <div className="max-w-3xl pt-8 sm:pt-14">
      <p className="text-xs font-semibold uppercase tracking-[0.2em]" style={{ color: "var(--accent-ink)" }}>Methodology</p>
      <h1 className="font-display mt-3 text-4xl font-semibold leading-tight tracking-tight sm:text-5xl" style={{ color: "var(--brand)" }}>
        How reviews are verified and ranked
      </h1>
      <p className="mt-5 text-lg leading-relaxed muted">
        Afefehub only publishes reviews people recorded themselves. This page explains what is checked, what the AI
        does and does not do, and how lists of the best-reviewed places are put together.
      </p>
      {SECTIONS.map((s) => (
        <section key={s.id} id={s.id} className="mt-10" aria-labelledby={`${s.id}-title`}>
          <h2 id={`${s.id}-title`} className="font-display text-2xl font-semibold" style={{ color: "var(--brand)" }}>
            {s.title}
          </h2>
          <div className="mt-3 leading-relaxed muted">{s.body}</div>
        </section>
      ))}
    </div>
  );
}
