"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import SearchBox, { type SearchState } from "@/components/SearchBox";
import ResultCard from "@/components/ResultCard";
import PlaceCandidateCard from "@/components/PlaceCandidateCard";
import HowToSubmit from "@/components/HowToSubmit";
import { SkeletonCard } from "@/components/Skeleton";
import { ApiError, lookupPlaces, searchBusinesses } from "@/lib/api";
import type { PlaceCandidate, SearchResult } from "@/lib/types";

type Status = "idle" | "loading" | "done" | "error";
type GoogleStatus = "idle" | "loading" | "done" | "error";

const MIN_GOOGLE_QUERY = 2;

export default function HomePage() {
  const [state, setState] = useState<SearchState>({ q: "", country: "", category: "" });
  const [results, setResults] = useState<SearchResult[]>([]);
  const [status, setStatus] = useState<Status>("idle");
  const [error, setError] = useState<string | null>(null);
  const [googleStatus, setGoogleStatus] = useState<GoogleStatus>("idle");
  const [googleError, setGoogleError] = useState<string | null>(null);
  const [candidates, setCandidates] = useState<PlaceCandidate[]>([]);
  const abortRef = useRef<AbortController | null>(null);
  const googleAbortRef = useRef<AbortController | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const resetGoogle = useCallback(() => {
    googleAbortRef.current?.abort();
    setCandidates([]);
    setGoogleStatus("idle");
    setGoogleError(null);
  }, []);

  // Google Places is only consulted when Afefehub has nothing: explicitly (button) or on Enter/Search.
  const checkGoogle = useCallback(async (s: SearchState) => {
    const q = s.q.trim();
    if (q.length < MIN_GOOGLE_QUERY) return;
    googleAbortRef.current?.abort();
    const ctrl = new AbortController();
    googleAbortRef.current = ctrl;
    setGoogleStatus("loading");
    setGoogleError(null);
    try {
      const res = await lookupPlaces({ q, country: s.country }, ctrl.signal);
      if (ctrl.signal.aborted) return;
      setCandidates(res.candidates);
      setGoogleStatus("done");
    } catch (e) {
      if (ctrl.signal.aborted) return;
      if (e instanceof ApiError && (e.status === 429 || e.status === 503)) setGoogleError("Google lookups are busy right now. Try again in a moment.");
      else setGoogleError(e instanceof Error ? e.message : "Something went wrong");
      setGoogleStatus("error");
    }
  }, []);

  const run = useCallback(
    async (s: SearchState, { allowGoogle }: { allowGoogle: boolean }) => {
      abortRef.current?.abort();
      resetGoogle();
      if (!s.q.trim() && !s.country && !s.category) {
        setResults([]);
        setStatus("idle");
        setError(null);
        return;
      }
      const ctrl = new AbortController();
      abortRef.current = ctrl;
      setStatus("loading");
      setError(null);
      try {
        const res = await searchBusinesses({ q: s.q.trim(), country: s.country, category: s.category }, ctrl.signal);
        if (ctrl.signal.aborted) return;
        setResults(res.results);
        setStatus("done");
        if (allowGoogle && res.results.length === 0) void checkGoogle(s);
      } catch (e) {
        if (ctrl.signal.aborted) return;
        setError(e instanceof Error ? e.message : "Something went wrong");
        setStatus("error");
      }
    },
    [checkGoogle, resetGoogle],
  );

  // Debounced search on every change (never calls Google); Enter/button searches immediately and may fall through to Google.
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => run(state, { allowGoogle: false }), 350);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [state, run]);

  const submitNow = () => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    run(state, { allowGoogle: true });
  };

  const hasQuery = Boolean(state.q.trim() || state.country || state.category);
  const trimmedQ = state.q.trim();
  const canCheckGoogle = trimmedQ.length >= MIN_GOOGLE_QUERY;
  const showEmpty = status === "done" && results.length === 0 && hasQuery;
  const showingCandidates = showEmpty && googleStatus === "done" && candidates.length > 0;

  return (
    <div className="pt-8 sm:pt-14">
      <section className="max-w-3xl">
        <p className="text-xs font-semibold uppercase tracking-[0.2em]" style={{ color: "var(--accent-ink)" }}>
          Video &amp; voice reviews · Africa
        </p>
        <h1 className="font-display mt-3 text-4xl font-semibold leading-[1.05] tracking-tight sm:text-6xl" style={{ color: "var(--brand)" }}>
          Real reviews from real voices.
        </h1>
        <p className="mt-4 max-w-xl text-base leading-relaxed muted sm:text-lg">
          Find businesses across Africa reviewed by real people. Every review is a public Instagram reel by a
          real person, or a voice note in their own words, checked and summarised by AI.
        </p>
      </section>

      <div className="mt-8 max-w-3xl">
        <SearchBox value={state} onChange={setState} onSubmit={submitNow} busy={status === "loading"} />
      </div>

      <section className="mt-8 max-w-3xl" aria-live="polite" aria-busy={status === "loading" || googleStatus === "loading"}>
        {status === "loading" && (
          <ul className="grid gap-3">
            <SkeletonCard />
            <SkeletonCard />
          </ul>
        )}
        {status === "error" && (
          <div className="card border-[var(--color-bad)] p-5 text-sm">
            <p className="font-semibold" style={{ color: "var(--color-bad)" }}>Couldn&apos;t reach the Afefehub API.</p>
            <p className="mt-1 muted">{error}</p>
            <button type="button" onClick={submitNow} className="mt-3 rounded-full border line px-4 py-1.5 text-sm font-medium">
              Try again
            </button>
          </div>
        )}
        {status === "done" && results.length > 0 && (
          <>
            <p className="mb-3 text-sm muted">
              {results.length} {results.length === 1 ? "business" : "businesses"} found
            </p>
            <ul className="grid gap-3">
              {results.map((r) => (
                <ResultCard key={r.business_id} result={r} />
              ))}
            </ul>
          </>
        )}
        {showEmpty && (
          <div className="card p-6">
            <p className="font-display text-lg font-semibold">Nothing here yet.</p>
            <p className="mt-1 text-sm muted">
              No business on Afefehub matches that search. Know a good one? Review it on video or send a voice note and it will show up here.
            </p>

            <div className="mt-4 flex flex-wrap items-center gap-3">
              <button
                type="button"
                onClick={() => checkGoogle(state)}
                disabled={!canCheckGoogle || googleStatus === "loading"}
                className="inline-flex items-center gap-2 rounded-full px-4 py-2 text-sm font-semibold disabled:cursor-not-allowed disabled:opacity-50"
                style={{ background: "var(--accent)", color: "var(--accent-fg)" }}
              >
                {googleStatus === "loading" ? "Checking Google…" : canCheckGoogle ? `Check Google for “${trimmedQ}”` : "Check Google"}
              </button>
              {!canCheckGoogle && <span className="text-xs muted">Type a business name to check Google.</span>}
            </div>

            {googleStatus === "error" && (
              <p className="mt-3 text-sm" style={{ color: "var(--color-bad)" }}>{googleError}</p>
            )}
            {googleStatus === "done" && candidates.length === 0 && (
              <p className="mt-3 text-sm muted">Google doesn&apos;t know that business either. Check the spelling, or widen the country filter.</p>
            )}
          </div>
        )}
        {showingCandidates && (
          <div className="mt-5">
            <p className="mb-3 text-sm muted">
              Found on Google · {candidates.length} {candidates.length === 1 ? "place" : "places"}. No Afefehub reviews yet, but you can read their Google reviews.
            </p>
            <ul className="grid gap-3">
              {candidates.map((c) => (
                <PlaceCandidateCard key={c.place_id} candidate={c} />
              ))}
            </ul>
          </div>
        )}
      </section>

      <div className={`max-w-3xl ${(status === "done" && results.length > 0) || showingCandidates ? "mt-12" : "mt-8"}`}>
        <HowToSubmit compact={(status === "done" && results.length > 0) || showingCandidates} />
      </div>
    </div>
  );
}
