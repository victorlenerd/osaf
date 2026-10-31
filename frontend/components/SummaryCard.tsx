import type { Summary } from "@/lib/types";
import { formatDate, percent, pluralize } from "@/lib/format";
import { SentimentDot } from "./Badges";

function List({ title, items, tone }: { title: string; items: string[]; tone: "good" | "bad" | "star" }) {
  if (!items?.length) return null;
  const color = tone === "good" ? "var(--color-good)" : tone === "bad" ? "var(--color-bad)" : "var(--color-mixed)";
  const mark = tone === "good" ? "+" : tone === "bad" ? "–" : "★";
  return (
    <div>
      <h3 className="text-xs font-semibold uppercase tracking-wide muted">{title}</h3>
      <ul className="mt-2 space-y-1.5 text-sm">
        {items.map((it) => (
          <li key={it} className="flex gap-2">
            <span aria-hidden className="w-4 shrink-0 font-bold" style={{ color }}>{mark}</span>
            <span>{it}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export default function SummaryCard({ summary }: { summary: Summary | null }) {
  if (!summary) {
    return (
      <section className="card p-5 sm:p-6" aria-labelledby="summary-title">
        <h2 id="summary-title" className="font-display text-xl font-semibold" style={{ color: "var(--brand)" }}>
          AI summary
        </h2>
        <p className="mt-2 text-sm muted">
          A summary is generated after the first review. Send a public reel link or a voice note to the Afefehub
          WhatsApp number to start this business&apos;s story.
        </p>
      </section>
    );
  }

  const rate = Math.round(Math.max(0, Math.min(1, summary.recommendation_rate)) * 100);

  return (
    <section className="card overflow-hidden" aria-labelledby="summary-title">
      <div className="p-5 sm:p-6">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 id="summary-title" className="text-xs font-semibold uppercase tracking-[0.18em]" style={{ color: "var(--accent-ink)" }}>
            AI summary · {pluralize(summary.review_count, "review")}
          </h2>
          <SentimentDot sentiment={summary.overall_sentiment} withLabel />
        </div>
        <p className="font-display mt-2 text-xl font-semibold leading-snug sm:text-2xl">{summary.headline}</p>

        <div className="mt-5">
          <div className="flex items-baseline justify-between text-sm">
            <span className="font-medium">Would recommend</span>
            <span className="font-display text-2xl font-bold" style={{ color: "var(--accent-ink)" }}>{percent(summary.recommendation_rate)}</span>
          </div>
          <div
            className="mt-1.5 h-2.5 w-full overflow-hidden rounded-full"
            style={{ background: "var(--line)" }}
            role="meter"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={rate}
            aria-label="Recommendation rate"
          >
            <div className="h-full rounded-full" style={{ width: `${rate}%`, background: "linear-gradient(90deg, var(--color-yellow-600), var(--color-yellow-300))" }} />
          </div>
        </div>

        <div className="mt-6 grid gap-5 sm:grid-cols-3">
          <List title="Recurring praise" items={summary.recurring_praise} tone="good" />
          <List title="Recurring complaints" items={summary.recurring_complaints} tone="bad" />
          <List title="Standout items" items={summary.standout_items} tone="star" />
        </div>

        <p className="mt-6 text-xs muted">
          Updated {formatDate(summary.last_updated)} · last review {formatDate(summary.last_review_at)} · {summary.model_version}
        </p>
      </div>
    </section>
  );
}
