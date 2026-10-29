"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { ApiError, getBusiness } from "@/lib/api";
import type { BusinessResponse } from "@/lib/types";
import { categoryLabel, countryName } from "@/lib/constants";
import { mapsUrl, pluralize, percent } from "@/lib/format";
import { CategoryBadge, SentimentDot } from "@/components/Badges";
import SummaryCard from "@/components/SummaryCard";
import ReviewCard from "@/components/ReviewCard";
import HowToSubmit from "@/components/HowToSubmit";
import { SkeletonCard } from "@/components/Skeleton";

type State =
  | { status: "loading" }
  | { status: "missing" }
  | { status: "notfound" }
  | { status: "error"; message: string }
  | { status: "ready"; data: BusinessResponse };

export default function BusinessView() {
  const params = useSearchParams();
  const id = params.get("id");
  const [state, setState] = useState<State>({ status: "loading" });

  useEffect(() => {
    if (!id) {
      setState({ status: "missing" });
      return;
    }
    const ctrl = new AbortController();
    setState({ status: "loading" });
    getBusiness(id, ctrl.signal)
      .then((data) => {
        if (ctrl.signal.aborted) return;
        setState({ status: "ready", data });
        document.title = `${data.business.name} · Afefehub`;
      })
      .catch((e: unknown) => {
        if (ctrl.signal.aborted) return;
        if (e instanceof ApiError && e.status === 404) setState({ status: "notfound" });
        else setState({ status: "error", message: e instanceof Error ? e.message : "Something went wrong" });
      });
    return () => ctrl.abort();
  }, [id]);

  if (state.status === "loading") {
    return (
      <div className="grid gap-4 pt-8" aria-busy>
        <SkeletonCard lines={2} />
        <SkeletonCard lines={5} />
        <SkeletonCard lines={4} />
      </div>
    );
  }

  if (state.status === "missing" || state.status === "notfound") {
    return (
      <div className="card mx-auto mt-12 max-w-lg p-8 text-center">
        <p className="font-display text-2xl font-semibold" style={{ color: "var(--brand)" }}>
          {state.status === "missing" ? "No business selected" : "Business not found"}
        </p>
        <p className="mt-2 text-sm muted">
          {state.status === "missing"
            ? "Pick a business from search to see its reviews."
            : "This business may have been removed, or the link is wrong."}
        </p>
        <Link href="/" className="mt-5 inline-block rounded-full px-5 py-2 text-sm font-semibold" style={{ background: "var(--accent)", color: "var(--accent-fg)" }}>
          Back to search
        </Link>
      </div>
    );
  }

  if (state.status === "error") {
    return (
      <div className="card mx-auto mt-12 max-w-lg p-8 text-center">
        <p className="font-semibold" style={{ color: "var(--color-bad)" }}>Couldn&apos;t load this business.</p>
        <p className="mt-1 text-sm muted">{state.message}</p>
        <button type="button" onClick={() => setState({ status: "loading" })} className="mt-4 rounded-full border line px-4 py-1.5 text-sm font-medium">
          Try again
        </button>
      </div>
    );
  }

  const { business, summary, reviews } = state.data;
  const maps = mapsUrl({ lat: business.location?.lat, lng: business.location?.lng, name: business.name, address: business.formatted_address });

  return (
    <div className="pt-6 sm:pt-10">
      <nav aria-label="Breadcrumb" className="text-sm muted">
        <Link href="/" className="hover:underline">Search</Link>
        <span aria-hidden> / </span>
        <span>{categoryLabel(business.category)}</span>
      </nav>

      <header className="mt-3">
        <div className="flex flex-wrap items-center gap-2">
          <CategoryBadge category={business.category} />
          <SentimentDot sentiment={business.overall_sentiment} withLabel />
          <span className="text-xs muted">{countryName(business.country)}</span>
        </div>
        <h1 className="font-display mt-2 text-3xl font-semibold leading-tight tracking-tight sm:text-5xl" style={{ color: "var(--brand)" }}>
          {business.name}
        </h1>
        <p className="mt-2 text-base muted">{business.formatted_address}</p>
        <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2 text-sm">
          <a href={maps} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 font-medium underline-offset-2 hover:underline" style={{ color: "var(--accent)" }}>
            <svg aria-hidden width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 21s-7-6.2-7-11a7 7 0 0 1 14 0c0 4.8-7 11-7 11Z" /><circle cx="12" cy="10" r="2.5" />
            </svg>
            Open in Google Maps
          </a>
          <span className="muted">{pluralize(business.review_count, "video review")}</span>
          {business.review_count > 0 && (
            <span className="muted">
              {percent(business.recommend_rate)} recommend · {business.recommend_counts.yes} yes / {business.recommend_counts.maybe} maybe / {business.recommend_counts.no} no
            </span>
          )}
        </div>
      </header>

      <div className="mt-6">
        <SummaryCard summary={summary} />
      </div>

      <section className="mt-10" aria-labelledby="reviews-title">
        <div className="flex items-baseline justify-between">
          <h2 id="reviews-title" className="font-display text-2xl font-semibold" style={{ color: "var(--brand)" }}>
            Video reviews
          </h2>
          <span className="text-sm muted">{pluralize(reviews.length, "reel")}</span>
        </div>
        {reviews.length === 0 ? (
          <div className="card mt-4 p-6 text-center text-sm muted">No video reviews yet. Be the first.</div>
        ) : (
          <div className="mt-4 grid gap-5">
            {reviews.map((r) => (
              <ReviewCard key={r.review_id} review={r} />
            ))}
          </div>
        )}
      </section>

      <div className="mt-12">
        <HowToSubmit compact />
      </div>
    </div>
  );
}
