import Link from "next/link";
import type { SearchResult } from "@/lib/types";
import { percent, pluralize } from "@/lib/format";
import { CategoryBadge, SentimentDot } from "./Badges";

export default function ResultCard({ result }: { result: SearchResult }) {
  const hasReviews = result.review_count > 0;
  return (
    <li>
      <Link
        href={`/business?id=${encodeURIComponent(result.business_id)}`}
        className="card group block p-4 transition-transform hover:-translate-y-0.5 focus-visible:-translate-y-0.5 sm:p-5"
      >
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <h3 className="font-display text-lg font-semibold leading-snug group-hover:underline" style={{ color: "var(--brand)" }}>
              {result.name}
            </h3>
            <p className="mt-0.5 truncate text-sm muted">{result.formatted_address}</p>
          </div>
          <CategoryBadge category={result.category} />
        </div>

        {result.summary_headline ? (
          <p className="mt-3 text-sm leading-relaxed">{result.summary_headline}</p>
        ) : (
          <p className="mt-3 text-sm italic muted">No AI summary yet. Be the first to review on video.</p>
        )}

        <div className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-2 text-sm">
          <SentimentDot sentiment={result.overall_sentiment} withLabel />
          <span className="muted">{pluralize(result.review_count, "review")}</span>
          {hasReviews && (
            <span className="font-semibold" style={{ color: "var(--accent)" }}>
              {percent(result.recommend_rate)} recommend
            </span>
          )}
        </div>
      </Link>
    </li>
  );
}
