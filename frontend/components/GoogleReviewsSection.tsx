"use client";

import { useEffect, useState } from "react";
import { ApiError, getGooglePlace } from "@/lib/api";
import type { GooglePlaceResponse } from "@/lib/types";
import { pluralize } from "@/lib/format";
import GoogleSummaryCard from "./GoogleSummaryCard";
import GoogleReviewCard from "./GoogleReviewCard";
import { SkeletonCard } from "./Skeleton";

type Props =
  /** Data already fetched by the page (Google-only business page). */
  | { data: GooglePlaceResponse; placeId?: undefined; title?: string }
  /** Fetch lazily after mount, so Afefehub content never waits on Google. */
  | { placeId: string; data?: undefined; title?: string };

type Fetch =
  | { status: "loading" }
  | { status: "ready"; data: GooglePlaceResponse }
  | { status: "none" }
  | { status: "error"; message: string };

export default function GoogleReviewsSection(props: Props) {
  const { placeId, title = "On Google" } = props;
  const [fetched, setFetched] = useState<Fetch>({ status: "loading" });

  useEffect(() => {
    if (!placeId) return;
    const ctrl = new AbortController();
    setFetched({ status: "loading" });
    getGooglePlace(placeId, ctrl.signal)
      .then((data) => {
        if (!ctrl.signal.aborted) setFetched({ status: "ready", data });
      })
      .catch((e: unknown) => {
        if (ctrl.signal.aborted) return;
        if (e instanceof ApiError && e.status === 404) setFetched({ status: "none" });
        else if (e instanceof ApiError && (e.status === 429 || e.status === 503)) setFetched({ status: "error", message: "Google lookups are busy right now." });
        else setFetched({ status: "error", message: "Couldn't load Google reviews right now." });
      });
    return () => ctrl.abort();
  }, [placeId]);

  const data = props.data ?? (fetched.status === "ready" ? fetched.data : null);

  const heading = (
    <div className="flex items-baseline justify-between">
      <h2 id="google-reviews-title" className="font-display text-2xl font-semibold" style={{ color: "var(--brand)" }}>
        {title}
      </h2>
      {data && <span className="text-sm muted">{pluralize(data.reviews.length, "Google review")}</span>}
    </div>
  );

  if (!data) {
    if (props.data === undefined && fetched.status === "loading") {
      return (
        <section className="mt-10" aria-labelledby="google-reviews-title" aria-busy>
          {heading}
          <div className="mt-4 grid gap-4">
            <SkeletonCard lines={3} />
          </div>
        </section>
      );
    }
    if (fetched.status === "none") return null;
    return (
      <section className="mt-10" aria-labelledby="google-reviews-title">
        {heading}
        <p className="mt-3 text-sm muted">{fetched.status === "error" ? fetched.message : "No Google reviews available."}</p>
      </section>
    );
  }

  return (
    <section className="mt-10" aria-labelledby="google-reviews-title">
      {heading}
      <div className="mt-4">
        <GoogleSummaryCard summary={data.summary} />
      </div>
      {data.reviews.length === 0 ? (
        <div className="card mt-5 p-6 text-center text-sm muted">Google has no written reviews for this place yet.</div>
      ) : (
        <div className="mt-5 grid gap-4">
          {data.reviews.map((r, i) => (
            <GoogleReviewCard key={`${r.author_name}-${r.publish_time ?? i}`} review={r} />
          ))}
        </div>
      )}
      <p className="mt-4 flex flex-wrap items-center gap-x-2 text-xs muted">
        <span className="inline-flex items-center gap-1">
          <GoogleG />
          <span>
            {data.attribution || "Reviews from Google"} · summary by {data.summary.model_version}
          </span>
        </span>
        <span>· Review text is shown as written by its author.</span>
      </p>
    </section>
  );
}

/** Small "G" mark so the Google attribution is recognisable at a glance; the text next to it carries the required wordmark. */
function GoogleG() {
  return (
    <svg aria-hidden width="14" height="14" viewBox="0 0 48 48">
      <path fill="#EA4335" d="M24 9.5c3.5 0 6.6 1.2 9 3.5l6.7-6.7C35.6 2.5 30.2 0 24 0 14.6 0 6.5 5.4 2.6 13.2l7.8 6C12.3 13.3 17.7 9.5 24 9.5z" />
      <path fill="#4285F4" d="M46.5 24.5c0-1.6-.1-3.1-.4-4.5H24v9h12.7c-.6 3-2.3 5.5-4.8 7.2l7.5 5.8c4.4-4.1 7.1-10.1 7.1-17.5z" />
      <path fill="#FBBC05" d="M10.4 28.8A14.6 14.6 0 0 1 9.5 24c0-1.7.3-3.3.8-4.8l-7.8-6A24 24 0 0 0 0 24c0 3.9.9 7.5 2.6 10.8l7.8-6z" />
      <path fill="#34A853" d="M24 48c6.5 0 11.9-2.1 15.9-5.8l-7.5-5.8c-2.1 1.4-4.9 2.3-8.4 2.3-6.3 0-11.7-3.8-13.6-9.1l-7.8 6C6.5 42.6 14.6 48 24 48z" />
    </svg>
  );
}
