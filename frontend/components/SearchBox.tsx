"use client";

import { useEffect, useId, useRef, useState } from "react";
import { CATEGORIES, COUNTRIES } from "@/lib/constants";
import type { Category } from "@/lib/types";

export interface SearchState {
  q: string;
  country: string;
  category: Category | "";
}

interface Props {
  value: SearchState;
  onChange: (next: SearchState) => void;
  onSubmit: () => void;
  busy?: boolean;
}

export default function SearchBox({ value, onChange, onSubmit, busy }: Props) {
  const inputId = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const [showAll, setShowAll] = useState(false);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  const visibleCategories = showAll ? CATEGORIES : CATEGORIES.slice(0, 8);

  return (
    <form
      role="search"
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit();
      }}
      className="card p-3 sm:p-4"
    >
      <label htmlFor={inputId} className="sr-only">
        Search businesses by name, address or keyword
      </label>
      <div className="flex flex-col gap-2 sm:flex-row">
        <div className="relative flex-1">
          <span aria-hidden className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 muted">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
              <circle cx="11" cy="11" r="7" />
              <path d="m20 20-3.5-3.5" />
            </svg>
          </span>
          <input
            ref={inputRef}
            id={inputId}
            type="search"
            inputMode="search"
            autoComplete="off"
            placeholder="Try “jollof in Yaba”, “barber Osu”, or a business name"
            value={value.q}
            onChange={(e) => onChange({ ...value, q: e.target.value })}
            className="h-12 w-full rounded-xl border line bg-transparent pl-10 pr-3 text-base outline-none placeholder:muted focus:border-[var(--accent)]"
          />
        </div>
        <select
          aria-label="Country"
          value={value.country}
          onChange={(e) => onChange({ ...value, country: e.target.value })}
          className="h-12 rounded-xl border line bg-transparent px-3 text-sm outline-none focus:border-[var(--accent)] sm:w-44"
        >
          <option value="">All countries</option>
          {COUNTRIES.map((c) => (
            <option key={c.code} value={c.code}>
              {c.name}
            </option>
          ))}
        </select>
        <button
          type="submit"
          disabled={busy}
          className="h-12 rounded-xl px-5 text-sm font-semibold transition-opacity disabled:opacity-60"
          style={{ background: "var(--accent)", color: "var(--accent-fg)" }}
        >
          {busy ? "Searching…" : "Search"}
        </button>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-2" role="group" aria-label="Filter by category">
        <button
          type="button"
          className="chip"
          aria-pressed={value.category === ""}
          onClick={() => onChange({ ...value, category: "" })}
        >
          All
        </button>
        {visibleCategories.map((c) => (
          <button
            key={c.value}
            type="button"
            className="chip"
            aria-pressed={value.category === c.value}
            onClick={() => onChange({ ...value, category: value.category === c.value ? "" : c.value })}
          >
            {c.label}
          </button>
        ))}
        <button type="button" className="text-xs font-medium underline-offset-2 hover:underline muted" onClick={() => setShowAll((s) => !s)}>
          {showAll ? "Fewer" : `+${CATEGORIES.length - 8} more`}
        </button>
      </div>
    </form>
  );
}
