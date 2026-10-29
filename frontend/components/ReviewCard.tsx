import type { Review } from "@/lib/types";
import { formatDate } from "@/lib/format";
import { languageName } from "@/lib/constants";
import { RecommendBadge, SentimentDot, Tag } from "./Badges";
import InstagramEmbed from "./InstagramEmbed";

function Bullets({ title, items, tone }: { title: string; items: string[]; tone: "good" | "bad" }) {
  if (!items?.length) return null;
  const color = tone === "good" ? "var(--color-good)" : "var(--color-bad)";
  return (
    <div>
      <h4 className="text-xs font-semibold uppercase tracking-wide muted">{title}</h4>
      <ul className="mt-1.5 space-y-1 text-sm">
        {items.map((it) => (
          <li key={it} className="flex gap-2">
            <span aria-hidden className="w-3 shrink-0 font-bold" style={{ color }}>{tone === "good" ? "+" : "–"}</span>
            <span>{it}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export default function ReviewCard({ review }: { review: Review }) {
  const x = review.extraction;
  const visitBits = [x.visit?.when_text, x.visit?.where_text].filter(Boolean) as string[];
  return (
    <article className="card overflow-hidden" aria-label={`Review by ${review.reviewer_display_name ?? "an Instagram reviewer"}`}>
      <div className="grid gap-0 md:grid-cols-[minmax(0,1fr)_320px]">
        <div className="p-5 sm:p-6">
          <div className="flex flex-wrap items-center gap-2">
            <RecommendBadge value={x.recommend} />
            <SentimentDot sentiment={x.overall_sentiment} withLabel />
            <Tag>{languageName(x.language)}</Tag>
          </div>
          <p className="font-display mt-3 text-lg font-semibold leading-snug">&ldquo;{x.one_line_summary}&rdquo;</p>
          <p className="mt-2 text-sm muted">
            {review.reviewer_display_name ?? "Instagram reviewer"} · {formatDate(review.created_at)}
            {visitBits.length > 0 && (
              <>
                {" "}· visited {visitBits.join(", ")}
                {x.visit?.when_iso ? ` (${formatDate(x.visit.when_iso)})` : ""}
              </>
            )}
          </p>

          <div className="mt-4 grid gap-4 sm:grid-cols-2">
            <Bullets title="What was good" items={x.good} tone="good" />
            <Bullets title="Could improve" items={x.improve} tone="bad" />
          </div>

          {x.keywords?.length > 0 && (
            <div className="mt-4 flex flex-wrap gap-1.5">
              {x.keywords.map((k) => (
                <Tag key={k}>#{k}</Tag>
              ))}
            </div>
          )}

          <a href={review.reel_url} target="_blank" rel="noreferrer" className="mt-4 inline-flex items-center gap-1 text-sm font-medium underline-offset-2 hover:underline" style={{ color: "var(--brand)" }}>
            Open on Instagram
            <svg aria-hidden width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M7 17 17 7M8 7h9v9" />
            </svg>
          </a>
        </div>
        <div className="border-t line p-3 md:border-l md:border-t-0" style={{ background: "color-mix(in oklab, var(--line) 35%, transparent)" }}>
          <InstagramEmbed url={review.reel_url} />
        </div>
      </div>
    </article>
  );
}
