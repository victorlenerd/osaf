"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import SearchBox, { type SearchState } from "@/components/SearchBox";
import ResultCard from "@/components/ResultCard";
import HowToSubmit from "@/components/HowToSubmit";
import { SkeletonCard } from "@/components/Skeleton";
import { searchBusinesses } from "@/lib/api";
import type { SearchResult } from "@/lib/types";

type Status = "idle" | "loading" | "done" | "error";

export default function HomePage() {
  const [state, setState] = useState<SearchState>({ q: "", country: "", category: "" });
  const [results, setResults] = useState<SearchResult[]>([]);
  const [status, setStatus] = useState<Status>("idle");
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const run = useCallback(async (s: SearchState) => {
    abortRef.current?.abort();
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
    } catch (e) {
      if (ctrl.signal.aborted) return;
      setError(e instanceof Error ? e.message : "Something went wrong");
      setStatus("error");
    }
  }, []);

  // Debounced search on every change; Enter/button searches immediately.
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => run(state), 350);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [state, run]);

  const submitNow = () => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    run(state);
  };

  const hasQuery = Boolean(state.q.trim() || state.country || state.category);

  return (
    <div className="pt-8 sm:pt-14">
      <section className="max-w-3xl">
        <p className="text-xs font-semibold uppercase tracking-[0.2em]" style={{ color: "var(--accent-ink)" }}>
          Video reviews · Africa
        </p>
        <h1 className="font-display mt-3 text-4xl font-semibold leading-[1.05] tracking-tight sm:text-6xl" style={{ color: "var(--brand)" }}>
          Real reviews from real faces.
        </h1>
        <p className="mt-4 max-w-xl text-base leading-relaxed muted sm:text-lg">
          Find businesses across Africa reviewed on video. Every review is a public Instagram reel by a real
          person, checked and summarised by AI.
        </p>
      </section>

      <div className="mt-8 max-w-3xl">
        <SearchBox value={state} onChange={setState} onSubmit={submitNow} busy={status === "loading"} />
      </div>

      <section className="mt-8 max-w-3xl" aria-live="polite" aria-busy={status === "loading"}>
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
        {status === "done" && results.length === 0 && hasQuery && (
          <div className="card p-6">
            <p className="font-display text-lg font-semibold">Nothing here yet.</p>
            <p className="mt-1 text-sm muted">
              No business matches that search. Know a good one? Review it on video and it will show up here.
            </p>
          </div>
        )}
      </section>

      <div className={`max-w-3xl ${status === "done" && results.length > 0 ? "mt-12" : "mt-8"}`}>
        <HowToSubmit compact={status === "done" && results.length > 0} />
      </div>
    </div>
  );
}
