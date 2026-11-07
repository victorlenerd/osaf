import type { Metadata } from "next";
import Link from "next/link";
import WhatsAppIcon from "@/components/WhatsAppIcon";
import { PAYOUTS_ENABLED, POINTS_PER_REVIEW, REWARD_LABEL, REWARD_POINTS, WHATSAPP_NUMBER } from "@/lib/constants";
import {
  AFEFEHUB_IG,
  CODE_DAYS,
  NGN_PER_POINT,
  OFFER_DAYS,
  PAYOUT_POOLS,
  POINTS,
  PRO_RATA_EXAMPLE,
  TIERS,
  WEEKLY_REVIEW_LIMIT,
  naira,
} from "@/lib/payouts";

export const metadata: Metadata = {
  title: "Reviewer payouts",
  description: `Get paid for honest reviews of businesses in Nigeria: up to ${naira(NGN_PER_POINT)} a point, paid monthly by bank transfer. How points, verification and the monthly pools work.`,
};

const STEPS: { title: string; body: React.ReactNode }[] = [
  {
    title: "Publish a review",
    body: (
      <>
        Send us a WhatsApp voice note about a business you visited in Nigeria, or the link to a public Instagram reel. We check it,
        confirm the details with you and publish it on Afefehub. You can publish up to {WEEKLY_REVIEW_LIMIT} reviews a week.
      </>
    ),
  },
  {
    title: "Reply ENTER",
    body: (
      <>
        Once it&rsquo;s published, we ask whether you want the review in this month&rsquo;s payout. Reply <strong>ENTER</strong> within{" "}
        {OFFER_DAYS} days. Only entered reviews earn points.
      </>
    ),
  },
  {
    title: "Prove the reel is yours (reels only)",
    body: (
      <>
        For a reel, we send you a code on WhatsApp. Send it as a direct message to <strong>@{AFEFEHUB_IG}</strong> on Instagram, from the
        account that posted the reel, within {CODE_DAYS} days. The usernames must match. After that, your later reels from that account
        count as yours automatically. An Instagram account can be linked to only one WhatsApp number.
      </>
    ),
  },
  {
    title: "Send your bank details",
    body: (
      <>
        The first time you enter, we ask for your bank name, 10-digit account number and account name. Prefer an Amazon gift card of
        the same value? Reply <strong>AMAZON</strong> instead.
      </>
    ),
  },
  {
    title: "Get paid after the month ends",
    body: (
      <>
        When the month is over, a person checks every entry. Then we pay by bank transfer to your Nigerian account and tell you on
        WhatsApp.
      </>
    ),
  },
];

const EARNS = [
  "The business is in Nigeria.",
  "You replied ENTER after the review was published.",
  "For reels: you posted the reel and verified it from that Instagram account, and you're on camera talking about your visit.",
  "It's your own review, not a copy of one already on Afefehub.",
];

const EARNS_NOTHING = [
  "A reel someone else posted. We may still publish it, credited to them, but it earns no points.",
  "A reel you didn't verify by the time we check that month's entries.",
  "A duplicate or near-duplicate of a review already on Afefehub. We compare the audio, the video and the words.",
  "Reviews of businesses outside Nigeria (they're still welcome on Afefehub).",
  "Spam or abuse. That gets the number banned and its unpaid points cancelled.",
];

const COMMANDS: { word: string; does: string }[] = [
  { word: "ENTER", does: "Enter the reviews we just published for you into this month's payout." },
  { word: "VERIFY", does: "Send a fresh Instagram verification code for your entered reels." },
  { word: "points", does: "See this month's entries, their points and status, and what you've been paid so far." },
  { word: "bank details", does: "Change the bank account we pay you to." },
  { word: "AMAZON", does: "Be paid with an Amazon gift card instead of a bank transfer." },
  { word: "delete my data", does: "Erase everything we hold about you. Points not yet paid are forfeited." },
];

const FAQ: { q: string; a: React.ReactNode }[] = [
  {
    q: "Does a good review earn more than a bad one?",
    a: "No. Points depend only on the kind of review: a voice note or your own verified reel. A glowing review and a grumpy one earn exactly the same. Payouts are a thank-you for taking part, never payment for an opinion.",
  },
  {
    q: "Why might I get less than ₦1,000 a point?",
    a: (
      <>
        Each category has a fixed pool every month. If the points in a category are worth more than its pool, everyone in that category
        is paid pro rata. For example, if restaurant reviews earn {PRO_RATA_EXAMPLE.points.toLocaleString("en-NG")} points in a month,
        the {naira(PRO_RATA_EXAMPLE.pool)} pool pays {naira(PRO_RATA_EXAMPLE.pool / PRO_RATA_EXAMPLE.points)} a point.
      </>
    ),
  },
  {
    q: "When do I get paid?",
    a: "After the month ends. We first have a person check every entry, then make the bank transfers and send you a WhatsApp message with the amount.",
  },
  {
    q: "Can I enter reviews I published before?",
    a: `No. You can enter a review only after we publish it, within ${OFFER_DAYS} days, by replying ENTER.`,
  },
  {
    q: "I live outside Nigeria. Can I take part?",
    a: "Payouts are only for reviews of businesses in Nigeria, paid to a Nigerian bank account (or as an Amazon gift card). You can still review businesses anywhere on Afefehub.",
  },
  {
    q: "What do you do with my bank details?",
    a: (
      <>
        We use them only to pay you. They&rsquo;re never published or shared with businesses, and they&rsquo;re deleted when you text{" "}
        <em>delete my data</em>. See the <Link href="/privacy">Privacy Policy</Link>.
      </>
    ),
  },
];

function Section({ id, title, children }: { id: string; title: string; children: React.ReactNode }) {
  return (
    <section className="mt-12" aria-labelledby={id}>
      <h2 id={id} className="font-display text-2xl font-semibold" style={{ color: "var(--brand)" }}>
        {title}
      </h2>
      {children}
    </section>
  );
}

export default function PayoutsPage() {
  // Before launch day the page describes the programme as coming, and says what applies today.
  const comingSoon = !PAYOUTS_ENABLED;
  const wa = WHATSAPP_NUMBER.replace(/[^\d]/g, "");

  return (
    <div className="max-w-3xl pt-8 sm:pt-14">
      <p className="flex flex-wrap items-center gap-2 text-xs font-semibold uppercase tracking-[0.2em]" style={{ color: "var(--accent-ink)" }}>
        {comingSoon && (
          <span className="rounded-full px-2 py-0.5 tracking-normal" style={{ background: "var(--accent)", color: "var(--accent-fg)" }}>
            Coming soon
          </span>
        )}
        Reviewer payouts · Nigeria
      </p>
      <h1 className="font-display mt-3 text-4xl font-semibold leading-tight tracking-tight sm:text-5xl" style={{ color: "var(--brand)" }}>
        Get paid for honest reviews.
      </h1>
      <p className="mt-5 text-lg leading-relaxed muted">
        {comingSoon ? "Soon you'll be able to review" : "Review"} businesses in Nigeria on Afefehub and earn points for every review you
        enter, glowing or grumpy. Each point is worth up to {naira(NGN_PER_POINT)}, paid once a month by bank transfer.
      </p>
      {comingSoon && (
        <div className="card mt-6 p-5" role="note">
          <p className="font-semibold">Payouts haven&rsquo;t started yet.</p>
          <p className="mt-1 text-sm leading-relaxed muted">
            This page describes how they will work. We&rsquo;ll post the start date here before they begin, and the full rules will be
            added to our <Link href="/terms">Terms</Link>. Until then nothing below applies yet: every published review earns{" "}
            {POINTS_PER_REVIEW} points under our current Terms, and {REWARD_POINTS} points earns a {REWARD_LABEL}.
          </p>
        </div>
      )}

      <Section id="points-title" title="Points per review">
        <ul className="mt-5 grid gap-3 sm:grid-cols-3" aria-label="Points per review">
          {TIERS.map((t) => (
            <li
              key={t.title}
              className="rounded-2xl border p-4"
              style={{
                background: t.featured ? "var(--accent)" : "var(--color-yellow-50)",
                color: t.featured ? "var(--accent-fg)" : "var(--fg)",
                borderColor: t.featured ? "var(--accent)" : "var(--color-yellow-200)",
              }}
            >
              <p className="font-display text-3xl font-bold tabular-nums leading-none">
                {t.points}
                <span className="ml-1 text-sm font-semibold">pts</span>
              </p>
              <p className="mt-3 text-sm font-semibold">{t.title}</p>
              <p className="mt-1 text-xs leading-relaxed" style={{ opacity: 0.8 }}>
                {t.detail}
              </p>
            </li>
          ))}
        </ul>
        <p className="mt-3 text-sm muted">
          A voice note earns {POINTS.voice} points ({naira(POINTS.voice * NGN_PER_POINT)} at the full rate). Your own verified reel earns{" "}
          {POINTS.reelAuthor} ({naira(POINTS.reelAuthor * NGN_PER_POINT)}).
        </p>
      </Section>

      <Section id="how-title" title="How it works">
        <ol className="mt-5 space-y-4">
          {STEPS.map((s, i) => (
            <li key={s.title} className="card flex gap-4 p-5">
              <span
                className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full font-display text-base font-bold"
                style={{ background: "var(--brand)", color: "var(--bg)" }}
                aria-hidden
              >
                {i + 1}
              </span>
              <div>
                <h3 className="font-semibold">{s.title}</h3>
                <p className="mt-1 text-sm leading-relaxed muted">{s.body}</p>
              </div>
            </li>
          ))}
        </ol>
      </Section>

      <Section id="pools-title" title="Monthly pools">
        <p className="mt-3 text-sm leading-relaxed muted">
          Each category group has its own pool every month. A point is worth {naira(NGN_PER_POINT)} until a pool runs short; then everyone in
          that group is paid pro rata, so the pool is shared fairly.
        </p>
        <dl className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
          {PAYOUT_POOLS.map((p) => (
            <div key={p.group} className="card px-4 py-3">
              <dt className="text-sm font-semibold">{p.group}</dt>
              <dd className="font-display mt-1 text-xl font-bold tabular-nums">{naira(p.ngn)}</dd>
              <dd className="mt-1 text-xs muted">{p.covers}</dd>
            </div>
          ))}
        </dl>
        <p className="mt-3 text-sm muted">
          Example: if restaurant reviews earn {PRO_RATA_EXAMPLE.points.toLocaleString("en-NG")} points in a month, the{" "}
          {naira(PRO_RATA_EXAMPLE.pool)} pool pays {naira(PRO_RATA_EXAMPLE.pool / PRO_RATA_EXAMPLE.points)} a point. A voice note then earns{" "}
          {naira((POINTS.voice * PRO_RATA_EXAMPLE.pool) / PRO_RATA_EXAMPLE.points)}.
        </p>
      </Section>

      <Section id="rules-title" title="What earns points">
        <div className="mt-5 grid gap-4 sm:grid-cols-2">
          <div className="card p-5">
            <h3 className="font-semibold">Earns points</h3>
            <ul className="mt-2 space-y-2 text-sm">
              {EARNS.map((t) => (
                <li key={t} className="flex gap-2">
                  <span aria-hidden className="w-3 shrink-0 font-bold" style={{ color: "var(--color-good)" }}>
                    +
                  </span>
                  <span>{t}</span>
                </li>
              ))}
            </ul>
          </div>
          <div className="card p-5">
            <h3 className="font-semibold">Earns nothing</h3>
            <ul className="mt-2 space-y-2 text-sm">
              {EARNS_NOTHING.map((t) => (
                <li key={t} className="flex gap-2">
                  <span aria-hidden className="w-3 shrink-0 font-bold" style={{ color: "var(--color-bad)" }}>
                    –
                  </span>
                  <span>{t}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </Section>

      <Section id="commands-title" title="Text us on WhatsApp">
        <dl className="card mt-5 divide-y line">
          {COMMANDS.map((c) => (
            <div key={c.word} className="flex flex-col gap-1 px-5 py-3 sm:flex-row sm:gap-4">
              <dt className="w-36 shrink-0 font-mono text-sm font-semibold">{c.word}</dt>
              <dd className="text-sm muted">{c.does}</dd>
            </div>
          ))}
        </dl>
      </Section>

      <Section id="faq-title" title="Questions">
        <div className="mt-5 space-y-3">
          {FAQ.map((f) => (
            <details key={f.q} className="card group p-5">
              <summary className="cursor-pointer list-none font-semibold">
                <span className="flex items-start justify-between gap-3">
                  {f.q}
                  <span aria-hidden className="muted transition-transform group-open:rotate-45">
                    +
                  </span>
                </span>
              </summary>
              <p className="mt-2 text-sm leading-relaxed muted">{f.a}</p>
            </details>
          ))}
        </div>
      </Section>

      <div className="card mt-12 flex flex-col items-start gap-4 p-6 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="font-display text-lg font-semibold" style={{ color: "var(--brand)" }}>
            Ready to start?
          </p>
          <p className="mt-1 text-sm muted">
            Send your first voice note or reel link to {WHATSAPP_NUMBER}.{" "}
            {comingSoon ? "Our current" : "The full rules are in our"}{" "}
            <Link href="/terms" className="underline">
              Terms
            </Link>{" "}
            {comingSoon ? "apply until payouts start." : ""}
          </p>
        </div>
        <a
          href={`https://wa.me/${wa}`}
          target="_blank"
          rel="noreferrer"
          className="inline-flex shrink-0 items-center gap-2 rounded-full py-2.5 pl-3.5 pr-5 text-sm font-semibold"
          style={{ background: "#25D366", color: "#062b14" }}
        >
          <WhatsAppIcon size={18} />
          Review on WhatsApp
        </a>
      </div>
    </div>
  );
}
