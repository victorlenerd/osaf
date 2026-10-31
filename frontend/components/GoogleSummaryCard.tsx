import type { GoogleSummary } from "@/lib/types";
import { formatDate, pluralize } from "@/lib/format";
import { SentimentDot } from "./Badges";
import { List } from "./SummaryCard";
import Stars from "./Stars";

export default function GoogleSummaryCard({ summary }: { summary: GoogleSummary }) {
  const hasText = summary.headline.trim().length > 0;
  const hasLists = summary.recurring_praise.length + summary.recurring_complaints.length + summary.standout_items.length > 0;
  return (
    <section className="card overflow-hidden" aria-labelledby="google-summary-title">
      <div className="p-5 sm:p-6">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 id="google-summary-title" className="text-xs font-semibold uppercase tracking-[0.18em]" style={{ color: "var(--accent-ink)" }}>
            AI summary of Google reviews
          </h3>
          {hasText && <SentimentDot sentiment={summary.overall_sentiment} withLabel />}
        </div>

        {hasText ? (
          <p className="font-display mt-2 text-xl font-semibold leading-snug sm:text-2xl">{summary.headline}</p>
        ) : (
          <p className="mt-2 text-sm muted">Google has a star rating for this place but no written reviews to summarise yet.</p>
        )}

        <div className="mt-5 flex flex-wrap items-center justify-between gap-2 text-sm">
          <span className="font-medium">Google rating</span>
          <span className="inline-flex items-center gap-2">
            <Stars rating={summary.rating} size={18} />
            {summary.rating != null && (
              <span className="font-display text-2xl font-bold" style={{ color: "var(--accent-ink)" }}>{summary.rating.toFixed(1)}</span>
            )}
            <span className="muted">from {pluralize(summary.user_rating_count, "rating")}</span>
          </span>
        </div>

        {hasText && hasLists && (
          <div className="mt-6 grid gap-5 sm:grid-cols-3">
            <List title="Recurring praise" items={summary.recurring_praise} tone="good" />
            <List title="Recurring complaints" items={summary.recurring_complaints} tone="bad" />
            <List title="Standout items" items={summary.standout_items} tone="star" />
          </div>
        )}

        <p className="mt-6 text-xs muted">
          {hasText ? `Based on ${pluralize(summary.reviews_considered, "Google review")} · ` : ""}
          Generated {formatDate(summary.generated_at)} · {summary.model_version}
        </p>
      </div>
    </section>
  );
}
