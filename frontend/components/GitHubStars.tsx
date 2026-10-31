"use client";

import { useEffect, useState } from "react";

/** GitHub mark, drawn in the current text colour. */
function GitHubIcon({ size = 16 }: { size?: number }) {
  return (
    <svg viewBox="0 0 16 16" width={size} height={size} aria-hidden focusable="false" fill="currentColor">
      <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0 0 16 8c0-4.42-3.58-8-8-8z" />
    </svg>
  );
}

const STAR_PATH = "M8 .25a.75.75 0 0 1 .673.418l1.882 3.815 4.21.612a.75.75 0 0 1 .416 1.279l-3.046 2.97.719 4.192a.751.751 0 0 1-1.088.791L8 12.347l-3.766 1.98a.75.75 0 0 1-1.088-.79l.72-4.194L.818 6.374a.75.75 0 0 1 .416-1.28l4.21-.611L7.327.668A.75.75 0 0 1 8 .25Z";

const CACHE_TTL_MS = 60 * 60 * 1000;

/** "owner/name" from a github.com URL, or null for anything else. */
export function repoSlug(url: string): string | null {
  try {
    const u = new URL(url);
    if (u.hostname !== "github.com") return null;
    const [owner, name] = u.pathname.split("/").filter(Boolean);
    return owner && name ? `${owner}/${name.replace(/\.git$/, "")}` : null;
  } catch {
    return null;
  }
}

function formatStars(n: number): string {
  if (n >= 1000) return `${(n / 1000).toFixed(n >= 10000 ? 0 : 1).replace(/\.0$/, "")}k`;
  return String(n);
}

/** Reads the star count from a per-browser cache, then from the GitHub API. Null while loading or when unavailable. */
function useStarCount(slug: string | null): number | null {
  const [stars, setStars] = useState<number | null>(null);

  useEffect(() => {
    if (!slug) return;
    const key = `gh-stars:${slug}`;
    try {
      const cached = JSON.parse(localStorage.getItem(key) ?? "null") as { stars: number; at: number } | null;
      if (cached && Date.now() - cached.at < CACHE_TTL_MS) {
        setStars(cached.stars);
        return;
      }
    } catch {
      /* storage unavailable: fall through to the network */
    }

    const controller = new AbortController();
    fetch(`https://api.github.com/repos/${slug}`, {
      signal: controller.signal,
      headers: { accept: "application/vnd.github+json" },
    })
      .then((res) => (res.ok ? res.json() : null))
      .then((data: { stargazers_count?: number } | null) => {
        const count = data?.stargazers_count;
        if (typeof count !== "number") return;
        setStars(count);
        try {
          localStorage.setItem(key, JSON.stringify({ stars: count, at: Date.now() }));
        } catch {
          /* ignore */
        }
      })
      .catch(() => {
        /* offline, rate limited or blocked: show the link without a count */
      });
    return () => controller.abort();
  }, [slug]);

  return stars;
}

/** Footer badge linking to the repository, with its live star count when GitHub answers. */
export default function GitHubStars({ url, className }: { url: string; className?: string }) {
  const slug = repoSlug(url);
  const stars = useStarCount(slug);
  const label = stars == null ? "Source on GitHub" : `Source on GitHub, ${stars} stars`;

  return (
    <a
      href={url}
      target="_blank"
      rel="noreferrer"
      aria-label={label}
      title={label}
      className={`inline-flex items-center overflow-hidden rounded-md border text-xs font-medium leading-none line ${className ?? ""}`}
      style={{ color: "var(--fg)" }}
    >
      <span className="inline-flex items-center gap-1.5 px-2 py-1">
        <GitHubIcon />
        <span>GitHub</span>
      </span>
      {stars != null && (
        <span
          className="inline-flex items-center gap-1 border-l px-2 py-1 line tabular-nums"
          style={{ background: "color-mix(in oklab, var(--fg) 6%, transparent)" }}
        >
          <svg viewBox="0 0 16 16" width={12} height={12} aria-hidden focusable="false" fill="currentColor">
            <path d={STAR_PATH} />
          </svg>
          {formatStars(stars)}
        </span>
      )}
    </a>
  );
}
