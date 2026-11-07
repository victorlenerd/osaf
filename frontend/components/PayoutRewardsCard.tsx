import Link from "next/link";
import { NGN_PER_POINT, PAYOUT_POOLS, TIERS, WEEKLY_REVIEW_LIMIT, naira } from "@/lib/payouts";
import { POINTS_PER_REVIEW, REWARD_LABEL, REWARD_POINTS, WHATSAPP_NUMBER } from "@/lib/constants";
import WhatsAppIcon from "./WhatsAppIcon";

const STEPS: { title: string; body: string }[] = [
  { title: "Publish a review", body: "Of any business in Nigeria, by voice note or Instagram reel." },
  { title: "Reply ENTER", body: "When we ask if you want it in the next payout. Only entered reviews earn points." },
  { title: "Get paid monthly", body: "A person checks every entry, then we send a bank transfer to your Nigerian account." },
];

/**
 * The payout programme on the home page. Before launch (`comingSoon`) it is announced as coming,
 * and the scheme in force under the current Terms is stated alongside it.
 */
export default function PayoutRewardsCard({ comingSoon = false }: { comingSoon?: boolean }) {
  const waHref = WHATSAPP_NUMBER ? `https://wa.me/${WHATSAPP_NUMBER.replace(/[^\d]/g, "")}?text=${encodeURIComponent("points")}` : undefined;

  return (
    <section className="card overflow-hidden" aria-labelledby="rewards-title">
      <div className="p-5 sm:p-8">
        <div className="max-w-xl">
          <p className="flex flex-wrap items-center gap-2 text-xs font-semibold uppercase tracking-[0.2em] muted">
            {comingSoon && (
              <span className="rounded-full px-2 py-0.5 tracking-normal" style={{ background: "var(--accent)", color: "var(--accent-fg)" }}>
                Coming soon
              </span>
            )}
            Reviewer payouts · Nigeria
          </p>
          <h2 id="rewards-title" className="font-display mt-2 text-xl font-semibold sm:text-2xl" style={{ color: "var(--brand)" }}>
            {comingSoon ? "Up" : "Earn up"} to {naira(NGN_PER_POINT)} a point, paid monthly.
          </h2>
          <p className="mt-2 text-sm leading-relaxed muted">
            {comingSoon
              ? "We're starting monthly cash payouts for reviews of businesses in Nigeria, glowing or grumpy. Here's how they will work."
              : `Review businesses in Nigeria and earn points for every review you enter, glowing or grumpy. Up to ${WEEKLY_REVIEW_LIMIT} reviews a week.`}
          </p>
        </div>

        {comingSoon && (
          <p className="mt-4 rounded-xl border px-4 py-3 text-sm leading-relaxed" style={{ borderColor: "var(--color-yellow-200)", background: "var(--color-yellow-50)" }}>
            <strong>Payouts haven&rsquo;t started yet.</strong> Until they do, every published review earns {POINTS_PER_REVIEW} points under
            our current Terms, and {REWARD_POINTS} points earns a {REWARD_LABEL}.
          </p>
        )}

        <ul className="mt-6 grid gap-3 sm:grid-cols-3" aria-label="Points per review">
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

        <ol className="mt-6 grid gap-4 sm:grid-cols-3">
          {STEPS.map((s, i) => (
            <li key={s.title} className="flex gap-3">
              <span
                className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full font-display text-sm font-bold"
                style={{ background: "var(--brand)", color: "var(--bg)" }}
                aria-hidden
              >
                {i + 1}
              </span>
              <div>
                <p className="text-sm font-semibold">{s.title}</p>
                <p className="mt-0.5 text-xs leading-relaxed muted">{s.body}</p>
              </div>
            </li>
          ))}
        </ol>

        <div className="mt-6">
          <p className="text-sm font-semibold">Monthly pools</p>
          <dl className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-4">
            {PAYOUT_POOLS.map((p) => (
              <div key={p.group} className="rounded-xl border line px-3 py-2.5">
                <dt className="text-xs muted" title={p.covers}>
                  {p.group}
                </dt>
                <dd className="font-display text-base font-bold tabular-nums">{naira(p.ngn)}</dd>
              </div>
            ))}
          </dl>
          <p className="mt-2 text-xs leading-relaxed muted">
            Restaurants include street food and cafés. If a category&rsquo;s points add up to more than its pool, everyone in it is paid
            pro rata. Duplicates, spam and abuse earn nothing and can get you banned.
          </p>
        </div>

        <div className="mt-5 flex flex-wrap items-center gap-3 border-t line pt-5">
          {waHref ? (
            <a
              href={waHref}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-2 rounded-full py-2 pl-3 pr-4 text-sm font-semibold"
              style={{ background: "#25D366", color: "#062b14" }}
            >
              <WhatsAppIcon size={18} />
              Text &ldquo;points&rdquo; to see your {comingSoon ? "balance" : "entries"}
            </a>
          ) : (
            <span className="text-sm muted">
              Text <strong>points</strong> to the Afefehub WhatsApp number to see your {comingSoon ? "balance" : "entries"}.
            </span>
          )}
          <p className="text-xs muted">
            Same points for every opinion: a thank-you for taking part, never payment for what you say.{" "}
            <Link href="/payouts" className="underline">
              {comingSoon ? "How payouts will work" : "How payouts work"}
            </Link>
          </p>
        </div>
      </div>
    </section>
  );
}
