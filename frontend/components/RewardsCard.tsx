"use client";

import { useState } from "react";
import Link from "next/link";
import { POINTS_PER_REVIEW, REWARD_LABEL, REWARD_POINTS, WEEKLY_REVIEW_LIMIT, WHATSAPP_NUMBER } from "@/lib/constants";
import WhatsAppIcon from "./WhatsAppIcon";

const REVIEWS_NEEDED = Math.ceil(REWARD_POINTS / POINTS_PER_REVIEW);

function GiftIcon({ size = 18 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <rect x="3" y="8" width="18" height="4" rx="1" />
      <path d="M12 8v13" />
      <path d="M19 12v7a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2v-7" />
      <path d="M7.5 8a2.5 2.5 0 0 1 0-5C11 3 12 8 12 8s1-5 4.5-5a2.5 2.5 0 0 1 0 5" />
    </svg>
  );
}

function message(reviews: number): string {
  if (reviews === 0) return `Publish your first review and you're already ${POINTS_PER_REVIEW} points in.`;
  const left = REVIEWS_NEEDED - reviews;
  if (left <= 0) return `You've hit ${REWARD_POINTS} points. That's a ${REWARD_LABEL} with your name on it.`;
  const weeks = Math.ceil(left / WEEKLY_REVIEW_LIMIT);
  const reviewWord = left === 1 ? "review" : "reviews";
  const pace =
    left <= WEEKLY_REVIEW_LIMIT
      ? "You could get there this week."
      : `About ${weeks} weeks away at ${WEEKLY_REVIEW_LIMIT} reviews a week.`;
  return `${left} more ${reviewWord} to your ${REWARD_LABEL}. ${pace}`;
}

export default function RewardsCard() {
  const [reviews, setReviews] = useState(0);
  const points = reviews * POINTS_PER_REVIEW;
  const pct = Math.min(100, Math.round((points / REWARD_POINTS) * 100));
  const unlocked = points >= REWARD_POINTS;
  const waHref = WHATSAPP_NUMBER ? `https://wa.me/${WHATSAPP_NUMBER.replace(/[^\d]/g, "")}?text=${encodeURIComponent("points")}` : undefined;

  return (
    <section className="card overflow-hidden" aria-labelledby="rewards-title">
      <div className="p-5 sm:p-8">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="max-w-md">
            <p className="text-xs font-semibold uppercase tracking-[0.2em] muted">Reviewer rewards</p>
            <h2 id="rewards-title" className="font-display mt-2 text-xl font-semibold sm:text-2xl" style={{ color: "var(--brand)" }}>
              {REWARD_POINTS} points = a {REWARD_LABEL}.
            </h2>
            <p className="mt-2 text-sm leading-relaxed muted">
              Every published review earns {POINTS_PER_REVIEW} points, glowing or grumpy. Reach {REWARD_POINTS} and we send you a{" "}
              {REWARD_LABEL} as a thank-you.
            </p>
          </div>
          <div
            className="flex items-center gap-2 rounded-full px-4 py-2"
            style={{ background: unlocked ? "var(--accent)" : "var(--color-yellow-100)", color: unlocked ? "var(--accent-fg)" : "var(--fg)" }}
            aria-live="polite"
          >
            <GiftIcon size={18} />
            <span key={points} className="reward-pop font-display text-lg font-bold tabular-nums">
              {points}
            </span>
            <span className="text-sm font-medium">/ {REWARD_POINTS} pts</span>
          </div>
        </div>

        <div className="mt-6">
          <p className="text-sm font-semibold">Try it: how many reviews have you published?</p>
          <div className="mt-3 flex flex-wrap items-center gap-1.5" role="group" aria-label="Number of published reviews">
            <button
              type="button"
              onClick={() => setReviews(0)}
              aria-pressed={reviews === 0}
              className="reward-dot"
              aria-label="No reviews yet"
            >
              0
            </button>
            {Array.from({ length: REVIEWS_NEEDED }, (_, i) => i + 1).map((n) => (
              <button
                key={n}
                type="button"
                onClick={() => setReviews(n)}
                aria-pressed={reviews === n}
                data-filled={n <= reviews || undefined}
                className="reward-dot"
                aria-label={`${n} ${n === 1 ? "review" : "reviews"}, ${n * POINTS_PER_REVIEW} points`}
              >
                {n}
              </button>
            ))}
          </div>

          <div className="mt-4">
            <div
              className="reward-track"
              role="progressbar"
              aria-valuemin={0}
              aria-valuemax={REWARD_POINTS}
              aria-valuenow={points}
              aria-label="Points towards your gift card"
            >
              <div className="reward-fill" style={{ width: `${pct}%` }} />
              {Array.from({ length: REVIEWS_NEEDED - 1 }, (_, i) => (
                <span key={i} className="reward-tick" style={{ left: `${((i + 1) / REVIEWS_NEEDED) * 100}%` }} aria-hidden />
              ))}
              <span className={`reward-goal${unlocked ? " is-unlocked" : ""}`} aria-hidden>
                <GiftIcon size={14} />
              </span>
            </div>
            <div className="mt-1.5 flex justify-between text-xs muted">
              <span>0 pts</span>
              <span>{REWARD_POINTS} pts · {REWARD_LABEL}</span>
            </div>
          </div>

          <p key={reviews} className="reward-pop mt-4 text-sm font-medium" aria-live="polite">
            {unlocked && <span aria-hidden>🎉 </span>}
            {message(reviews)}
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
              Text “points” to check your real balance
            </a>
          ) : (
            <span className="text-sm muted">Text <strong>points</strong> to the Afefehub WhatsApp number to check your real balance.</span>
          )}
          <p className="text-xs muted">
            Same points for every opinion. A gift card is a thank-you, never payment for a review.{" "}
            <Link href="/terms#submitting" className="underline">Terms</Link>
          </p>
        </div>
      </div>
    </section>
  );
}
