import type { Recommend, Sentiment } from "@/lib/types";
import { categoryLabel } from "@/lib/constants";

const SENTIMENT_COLOR: Record<Sentiment, string> = {
  positive: "var(--color-good)",
  mixed: "var(--color-mixed)",
  negative: "var(--color-bad)",
};

const SENTIMENT_LABEL: Record<Sentiment, string> = {
  positive: "Mostly positive",
  mixed: "Mixed",
  negative: "Mostly negative",
};

export function SentimentDot({ sentiment, withLabel = false }: { sentiment: Sentiment | null; withLabel?: boolean }) {
  const color = sentiment ? SENTIMENT_COLOR[sentiment] : "var(--line)";
  const label = sentiment ? SENTIMENT_LABEL[sentiment] : "No reviews yet";
  return (
    <span className="inline-flex items-center gap-1.5 text-xs font-medium muted">
      <span
        aria-hidden
        className="inline-block h-2.5 w-2.5 rounded-full ring-2 ring-white/70 dark:ring-black/30"
        style={{ background: color }}
      />
      {withLabel ? <span>{label}</span> : <span className="sr-only">{label}</span>}
    </span>
  );
}

export function CategoryBadge({ category }: { category: string }) {
  return (
    <span
      className="inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold uppercase tracking-wide"
      style={{ background: "color-mix(in oklab, var(--brand) 14%, transparent)", color: "var(--brand)" }}
    >
      {categoryLabel(category)}
    </span>
  );
}

const RECOMMEND_STYLE: Record<Recommend, { bg: string; fg: string; label: string }> = {
  yes: { bg: "color-mix(in oklab, var(--color-good) 16%, transparent)", fg: "var(--color-good)", label: "Recommends" },
  maybe: { bg: "color-mix(in oklab, var(--color-mixed) 22%, transparent)", fg: "#8a5f0f", label: "Maybe" },
  no: { bg: "color-mix(in oklab, var(--color-bad) 14%, transparent)", fg: "var(--color-bad)", label: "Doesn't recommend" },
};

export function RecommendBadge({ value }: { value: Recommend }) {
  const s = RECOMMEND_STYLE[value] ?? RECOMMEND_STYLE.maybe;
  const icon = value === "yes" ? "👍" : value === "no" ? "👎" : "🤔";
  return (
    <span
      className="inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-semibold"
      style={{ background: s.bg, color: s.fg }}
    >
      <span aria-hidden>{icon}</span> {s.label}
    </span>
  );
}

export function Tag({ children }: { children: React.ReactNode }) {
  return (
    <span className="inline-flex items-center rounded-md border line px-2 py-0.5 text-xs muted">{children}</span>
  );
}
