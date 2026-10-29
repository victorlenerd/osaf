import type { Metadata } from "next";
import Link from "next/link";
import { REPO_URL } from "@/lib/constants";

export const metadata: Metadata = {
  title: "About",
  description: "What Afefehub is and how video reviews are verified with Meta's SAM 3.1, Muse Voice Transcribe and Muse Spark.",
};

const STEPS = [
  {
    title: "Public reel only",
    body: "A review must be a public Instagram reel. If the account or the post is private, it is not accepted, so every review on Afefehub can be watched by anyone.",
    model: "Instagram",
  },
  {
    title: "A real, talking face",
    body: "We run Meta SAM 3.1 over the video to confirm there is a person on camera who is actually speaking. Screen recordings, slideshows and voice-overs with no face are rejected.",
    model: "Meta SAM 3.1",
  },
  {
    title: "Word-for-word transcript",
    body: "Muse Voice Transcribe turns the audio into text in the language it was spoken, including English, French, Swahili and Nigerian Pidgin.",
    model: "Muse Voice Transcribe",
  },
  {
    title: "Structured extraction",
    body: "Muse Spark reads the transcript and pulls out the business, when and where the visit happened, what was good, what could improve, and whether the reviewer recommends it.",
    model: "Muse Spark 1.3",
  },
  {
    title: "A living summary",
    body: "Each new review is added to that business's history, and the AI summary on its page is regenerated so it always reflects every review to date.",
    model: "Muse Spark 1.3",
  },
];

export default function AboutPage() {
  return (
    <div className="mx-auto max-w-3xl pt-8 sm:pt-14">
      <p className="text-xs font-semibold uppercase tracking-[0.2em]" style={{ color: "var(--accent)" }}>About</p>
      <h1 className="font-display mt-3 text-4xl font-semibold leading-tight tracking-tight sm:text-5xl" style={{ color: "var(--brand)" }}>
        Reviews you can look in the eye.
      </h1>
      <p className="mt-5 text-lg leading-relaxed muted">
        Afefehub is a place to discover businesses across Africa through authentic video reviews. Instead of anonymous
        star ratings, every review is a public Instagram reel of a real person talking about a real visit. We turn those
        reels into searchable, structured reviews and a running AI summary for each business.
      </p>

      <section className="mt-12" aria-labelledby="how-title">
        <h2 id="how-title" className="font-display text-2xl font-semibold" style={{ color: "var(--brand)" }}>
          How verification works
        </h2>
        <ol className="mt-5 space-y-4">
          {STEPS.map((s, i) => (
            <li key={s.title} className="card flex gap-4 p-5">
              <span
                className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full font-display text-base font-bold"
                style={{ background: "var(--brand)", color: "var(--bg)" }}
              >
                {i + 1}
              </span>
              <div>
                <div className="flex flex-wrap items-center gap-2">
                  <h3 className="font-semibold">{s.title}</h3>
                  <span className="rounded-full border line px-2 py-0.5 text-xs muted">{s.model}</span>
                </div>
                <p className="mt-1 text-sm leading-relaxed muted">{s.body}</p>
              </div>
            </li>
          ))}
        </ol>
      </section>

      <section className="mt-12" aria-labelledby="submit-title">
        <h2 id="submit-title" className="font-display text-2xl font-semibold" style={{ color: "var(--brand)" }}>
          Submitting a review
        </h2>
        <p className="mt-3 leading-relaxed muted">
          Post your reel publicly, then send the link to the Afefehub WhatsApp number shown on the{" "}
          <Link href="/" className="underline" style={{ color: "var(--accent)" }}>home page</Link>. There is no app to
          install and no account to create. Within a few minutes the review appears on the business page with your reel
          embedded.
        </p>
      </section>

      <section className="mt-12" aria-labelledby="oss-title">
        <h2 id="oss-title" className="font-display text-2xl font-semibold" style={{ color: "var(--brand)" }}>
          Open source
        </h2>
        <p className="mt-3 leading-relaxed muted">
          Afefehub was built for the Meta Global AI Developer Hackathon and is open source. The agent, the API and this
          site are all in one repository.
        </p>
        <a
          href={REPO_URL || "#"}
          target={REPO_URL ? "_blank" : undefined}
          rel="noreferrer"
          className="mt-4 inline-flex items-center gap-2 rounded-full px-5 py-2 text-sm font-semibold"
          style={{ background: "var(--accent)", color: "var(--accent-fg)" }}
        >
          {REPO_URL ? "View the repository" : "Repository link coming soon"}
        </a>
      </section>
    </div>
  );
}
