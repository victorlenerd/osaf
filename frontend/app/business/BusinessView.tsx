"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { ApiError, getBusiness, getGooglePlace } from "@/lib/api";
import type { BusinessResponse, GooglePlaceResponse } from "@/lib/types";
import { categoryLabel, countryName, placeTypeLabel } from "@/lib/constants";
import { mapsUrl, pluralize, percent } from "@/lib/format";
import { CategoryBadge, SentimentDot, Tag } from "@/components/Badges";
import SummaryCard from "@/components/SummaryCard";
import ReviewCard from "@/components/ReviewCard";
import HowToSubmit from "@/components/HowToSubmit";
import GoogleReviewsSection from "@/components/GoogleReviewsSection";
import { ClosedPill, GoogleVerifiedPill } from "@/components/PlaceCandidateCard";
import Stars from "@/components/Stars";
import { SkeletonCard } from "@/components/Skeleton";

type State =
  | { status: "loading" }
  | { status: "missing" }
  | { status: "notfound" }
  | { status: "error"; message: string }
  | { status: "ready"; data: BusinessResponse }
  /** Known to Google but not (yet) reviewed on Afefehub: show its live Google reviews instead. */
  | { status: "google-only"; data: GooglePlaceResponse };

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
      .catch(async (e: unknown) => {
        if (ctrl.signal.aborted) return;
        if (e instanceof ApiError && e.status === 404) {
          // User-sourced ids (afefe:...) can never be on Google; everything else is a Google place id.
          if (id.startsWith("afefe:")) {
            setState({ status: "notfound" });
            return;
          }
          try {
            const data = await getGooglePlace(id, ctrl.signal);
            if (ctrl.signal.aborted) return;
            setState({ status: "google-only", data });
            document.title = `${data.place.name} · Afefehub`;
          } catch (ge: unknown) {
            if (ctrl.signal.aborted) return;
            if (ge instanceof ApiError && ge.status === 404) setState({ status: "notfound" });
            else setState({ status: "error", message: ge instanceof Error ? ge.message : "Something went wrong" });
          }
          return;
        }
        setState({ status: "error", message: e instanceof Error ? e.message : "Something went wrong" });
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

  if (state.status === "google-only") {
    return <GoogleOnlyPage data={state.data} />;
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
          <a href={maps} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 font-medium underline-offset-2 hover:underline" style={{ color: "var(--accent-ink)" }}>
            <svg aria-hidden width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 21s-7-6.2-7-11a7 7 0 0 1 14 0c0 4.8-7 11-7 11Z" /><circle cx="12" cy="10" r="2.5" />
            </svg>
            Open in Google Maps
          </a>
          <span className="muted">{pluralize(business.review_count, "review")}</span>
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
            Reviews
          </h2>
          <span className="text-sm muted">{pluralize(reviews.length, "review")}</span>
        </div>
        {reviews.length === 0 ? (
          <div className="card mt-4 p-6 text-center text-sm muted">No reviews yet. Be the first.</div>
        ) : (
          <div className="mt-4 grid gap-5">
            {reviews.map((r) => (
              <ReviewCard key={r.review_id} review={r} />
            ))}
          </div>
        )}
      </section>

      {business.source === "google" && <GoogleReviewsSection placeId={business.business_id} />}

      <div className="mt-12">
        <HowToSubmit compact />
      </div>
    </div>
  );
}

function GoogleOnlyPage({ data }: { data: GooglePlaceResponse }) {
  const { place } = data;
  const closed = place.business_status === "CLOSED_PERMANENTLY";
  const maps = place.google_maps_uri ?? mapsUrl({ lat: place.lat ?? undefined, lng: place.lng ?? undefined, name: place.name, address: place.formatted_address });
  const type = placeTypeLabel(place.primary_type);

  return (
    <div className="pt-6 sm:pt-10">
      <nav aria-label="Breadcrumb" className="text-sm muted">
        <Link href="/" className="hover:underline">Search</Link>
        <span aria-hidden> / </span>
        <span>{type || "Found on Google"}</span>
      </nav>

      <header className="mt-3">
        <div className="flex flex-wrap items-center gap-2">
          <GoogleVerifiedPill />
          {closed && <ClosedPill />}
          {type && <Tag>{type}</Tag>}
          {place.country && <span className="text-xs muted">{countryName(place.country)}</span>}
        </div>
        <h1 className="font-display mt-2 text-3xl font-semibold leading-tight tracking-tight sm:text-5xl" style={{ color: "var(--brand)" }}>
          {place.name}
        </h1>
        <p className="mt-2 text-base muted">{place.formatted_address}</p>
        <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2 text-sm">
          <a href={maps} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 font-medium underline-offset-2 hover:underline" style={{ color: "var(--accent-ink)" }}>
            <svg aria-hidden width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 21s-7-6.2-7-11a7 7 0 0 1 14 0c0 4.8-7 11-7 11Z" /><circle cx="12" cy="10" r="2.5" />
            </svg>
            Open in Google Maps
          </a>
          <span className="inline-flex items-center gap-2">
            <Stars rating={place.rating} size={16} withValue />
            <span className="muted">{pluralize(place.user_rating_count, "Google rating")}</span>
          </span>
          <span className="muted">No Afefehub reviews yet</span>
        </div>
      </header>

      <GoogleReviewsSection data={data} title="On Google" />

      {!closed && (
        <div className="mt-12">
          <p className="mb-3 font-display text-lg font-semibold" style={{ color: "var(--brand)" }}>
            Be the first to review this business on Afefehub.
          </p>
          <HowToSubmit compact />
        </div>
      )}
    </div>
  );
}
