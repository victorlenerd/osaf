import type { Metadata } from "next";
import Link from "next/link";
import WhatsAppIcon from "@/components/WhatsAppIcon";
import { WHATSAPP_NUMBER } from "@/lib/constants";
import { LEGAL } from "@/lib/legal";

export const metadata: Metadata = {
  title: "Delete your data",
  description: `How to delete everything ${LEGAL.brand} holds about you: your reviews, videos, voice notes, transcripts, chat history, payout entries and bank details. Self-service from WhatsApp, or by email.`,
};

const B = LEGAL.brand;
const DELETE_COMMAND = "delete my data";
const CONFIRM_WORD = "DELETE";
const WINDOW_MINUTES = 10;

const DELETED: { what: string; detail: string }[] = [
  { what: "Your published reviews", detail: "Every review you submitted is removed from the business pages and from search right away." },
  { what: "Videos, voice notes and transcripts", detail: "Our stored copies of your reels, voice notes, audio, transcripts and the AI agent's working notes, and the fingerprints we use to spot duplicates." },
  { what: "Submissions in progress", detail: "Anything you sent that was still being processed, was rejected, or was abandoned." },
  { what: "Your WhatsApp conversation", detail: "The record of your chats with the Afefehub number, including your WhatsApp profile name and country." },
  { what: "Your payout entries and points", detail: "Every entry not yet paid, with its points. Unpaid points are forfeited and cannot be restored after deletion." },
  { what: "Your bank details", detail: "The bank name, account number and account name you gave us for payouts, or your choice of a gift card." },
  { what: "Your Instagram verification", detail: "Any pending verification code, and the link between your verified Instagram account and your number." },
];

const STEPS: { title: string; body: string }[] = [
  {
    title: `Message “${DELETE_COMMAND}” to the ${B} number`,
    body: "Send it from the same WhatsApp number you used to submit your reviews. We reply with exactly what will be deleted: how many reviews, how many payout entries, and what else we hold.",
  },
  {
    title: `Reply ${CONFIRM_WORD}, in capitals`,
    body: `You have ${WINDOW_MINUTES} minutes to confirm. Reply anything else, or nothing at all, and your data stays as it is. Nothing is deleted until you confirm.`,
  },
  {
    title: "Receive your confirmation",
    body: "Within a minute we confirm the deletion and give you a reference number. Your reviews are already gone from afefehub.com by then. Keep the reference in case you ever need to ask us about the request.",
  },
];

export default function DataDeletionPage() {
  const number = WHATSAPP_NUMBER || "the Afefehub WhatsApp number";
  const waHref = WHATSAPP_NUMBER
    ? `https://wa.me/${WHATSAPP_NUMBER.replace(/[^\d]/g, "")}?text=${encodeURIComponent(DELETE_COMMAND)}`
    : undefined;

  return (
    <div className="max-w-3xl pt-8 sm:pt-14">
      <p className="text-xs font-semibold uppercase tracking-[0.2em]" style={{ color: "var(--accent-ink)" }}>
        Your data
      </p>
      <h1 className="font-display mt-3 text-4xl font-semibold leading-tight tracking-tight sm:text-5xl" style={{ color: "var(--brand)" }}>
        Delete your data
      </h1>
      <p className="mt-5 text-lg leading-relaxed muted">
        You can erase everything {B} holds about you at any time, without asking anyone. There is no account to log
        into: your WhatsApp number is your identity, so the deletion happens from the same number. If you cannot use
        that number any more, or you appear in someone else&rsquo;s review, email us instead.
      </p>

      <section className="mt-10" aria-labelledby="how-title">
        <h2 id="how-title" className="font-display text-2xl font-semibold" style={{ color: "var(--brand)" }}>
          Delete it yourself, from WhatsApp
        </h2>
        <p className="mt-2 text-sm muted">Takes about a minute. Works 24 hours a day and needs no one at {B} to approve it.</p>
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
                <h3 className="font-semibold">{s.title}</h3>
                <p className="mt-1 text-sm leading-relaxed muted">{s.body}</p>
              </div>
            </li>
          ))}
        </ol>
        <div className="mt-5 flex flex-wrap items-center gap-3">
          {waHref ? (
            <a
              href={waHref}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-2 rounded-full py-2 pl-3 pr-4 text-sm font-semibold"
              style={{ background: "#25D366", color: "#062b14" }}
              aria-label={`Open WhatsApp and send “${DELETE_COMMAND}” to ${number}`}
            >
              <WhatsAppIcon size={18} />
              Send &ldquo;{DELETE_COMMAND}&rdquo; to {number}
            </a>
          ) : (
            <code className="rounded-full border line px-4 py-2 text-sm font-semibold">{DELETE_COMMAND}</code>
          )}
          <span className="text-xs muted">Opens WhatsApp with the message ready. You still confirm with {CONFIRM_WORD} afterwards.</span>
        </div>
      </section>

      <section className="mt-12" aria-labelledby="what-title">
        <h2 id="what-title" className="font-display text-2xl font-semibold" style={{ color: "var(--brand)" }}>
          What gets deleted
        </h2>
        <ul className="card mt-5 divide-y line px-5 sm:px-6">
          {DELETED.map((d) => (
            <li key={d.what} className="py-4">
              <p className="font-semibold">{d.what}</p>
              <p className="mt-0.5 text-sm leading-relaxed muted">{d.detail}</p>
            </li>
          ))}
        </ul>
        <p className="mt-4 text-sm leading-relaxed muted">
          Business pages you reviewed stay, because they describe the business and not you, but their review count,
          recommendation rate and AI summary are recalculated without your review. A business whose only review was
          yours is removed altogether. Your reel on Instagram is yours and is not affected.
        </p>
      </section>

      <section className="mt-12" aria-labelledby="after-title">
        <h2 id="after-title" className="font-display text-2xl font-semibold" style={{ color: "var(--brand)" }}>
          What we keep, and for how long
        </h2>
        <ul className="legal-section mt-4 space-y-2 text-[15px] leading-relaxed">
          <li>
            <strong>Nothing that identifies you.</strong> Your phone number is removed from every record. We keep a dated
            receipt of the deletion under your reference number, containing a keyed one-way hash of the number and the
            counts of what was removed, for 12 months, so we can prove the request was honoured.
          </li>
          <li>
            <strong>Payments already made.</strong> If we have already paid you, we keep the record of each payment (the amount,
            the date and the reviews it covered) for accounting, with your phone number removed. Your bank details are not kept.
          </li>
          <li>
            <strong>Bans.</strong> If your number was banned for spam or abuse, we keep a one-way hash
            of it so the ban still applies. It is used only for fraud prevention.
          </li>
          <li>
            <strong>Backups</strong> are overwritten on a 35-day cycle. Deleted data disappears from them on that schedule and is
            never restored into the live service.
          </li>
          <li>
            <strong>Copies elsewhere.</strong> If someone saved or shared the public afefehub.com page before you deleted your
            review, we cannot recall that copy, and search engines may take a few days to drop their cached version.
          </li>
          <li>
            <strong>Emails you sent us</strong> about a request are kept for 3 years, as described in the{" "}
            <Link href="/privacy#retention">Privacy Policy</Link>.
          </li>
        </ul>
      </section>

      <section className="mt-12" aria-labelledby="email-title">
        <h2 id="email-title" className="font-display text-2xl font-semibold" style={{ color: "var(--brand)" }}>
          By email instead
        </h2>
        <div className="legal-section mt-4 space-y-3 text-[15px] leading-relaxed">
          <p>
            Email <a href={`mailto:${LEGAL.privacyEmail}?subject=${encodeURIComponent("Data deletion request")}`}>{LEGAL.privacyEmail}</a>{" "}
            if you no longer have access to the WhatsApp number you submitted with, if you would rather not use WhatsApp,
            or if you appear in a review you did not submit. Tell us:
          </p>
          <ul>
            <li>the phone number you submitted with, or a link to the review or business page you mean;</li>
            <li>whether you want everything deleted or only a particular review removed.</li>
          </ul>
          <p>
            Because we cannot see the sending number by email, we verify the request first, for example by asking you to
            confirm from the Instagram account that posted the reel. We respond within 30 days, usually much sooner, and
            send you the same reference number.
          </p>
        </div>
      </section>

      <section className="mt-12" aria-labelledby="more-title">
        <h2 id="more-title" className="font-display text-2xl font-semibold" style={{ color: "var(--brand)" }}>
          Only want one review gone?
        </h2>
        <p className="mt-3 text-[15px] leading-relaxed muted">
          Deleting your data removes all of your reviews. To withdraw a single review and keep the rest, message the {B}{" "}
          number and tell us which one, or email <a className="underline" href={`mailto:${LEGAL.privacyEmail}`}>{LEGAL.privacyEmail}</a>.
          The full picture of what we collect and why is in the <Link className="underline" href="/privacy">Privacy Policy</Link>;
          withdrawal of reviews is covered in section 10 of the <Link className="underline" href="/terms#removal">Terms of Service</Link>.
          {B} is operated by {LEGAL.operator}, {LEGAL.address}.
        </p>
      </section>
    </div>
  );
}
