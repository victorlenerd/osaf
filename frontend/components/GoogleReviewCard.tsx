import type { GoogleReview } from "@/lib/types";
import Stars from "./Stars";

export default function GoogleReviewCard({ review }: { review: GoogleReview }) {
  const text = review.text ?? "";
  const hasText = text.trim().length > 0;
  return (
    <article className="card p-5 sm:p-6" aria-label={`Google review by ${review.author_name}`}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-3">
          {review.author_photo_uri ? (
            // eslint-disable-next-line @next/next/no-img-element -- remote Google avatar, static export has no image optimiser
            <img src={review.author_photo_uri} alt="" width={36} height={36} className="h-9 w-9 rounded-full border line object-cover" referrerPolicy="no-referrer" />
          ) : (
            <span aria-hidden className="flex h-9 w-9 items-center justify-center rounded-full font-display text-sm font-bold" style={{ background: "var(--accent)", color: "var(--accent-fg)" }}>
              {review.author_name.trim().charAt(0).toUpperCase() || "?"}
            </span>
          )}
          <div className="min-w-0">
            {review.author_uri ? (
              <a href={review.author_uri} target="_blank" rel="noreferrer" className="font-semibold underline-offset-2 hover:underline" style={{ color: "var(--brand)" }}>
                {review.author_name}
              </a>
            ) : (
              <span className="font-semibold">{review.author_name}</span>
            )}
            <p className="text-xs muted">{review.relative_time}</p>
          </div>
        </div>
        <Stars rating={review.rating} size={16} />
      </div>

      {hasText ? (
        <p className="mt-4 whitespace-pre-line text-sm leading-relaxed">{text}</p>
      ) : (
        <p className="mt-4 text-sm italic muted">Rating only, no written review.</p>
      )}

      {review.google_maps_uri && (
        <a href={review.google_maps_uri} target="_blank" rel="noreferrer" className="mt-4 inline-flex items-center gap-1 text-sm font-medium underline-offset-2 hover:underline" style={{ color: "var(--brand)" }}>
          View on Google
          <svg aria-hidden width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M7 17 17 7M8 7h9v9" />
          </svg>
        </a>
      )}
    </article>
  );
}
