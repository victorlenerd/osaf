"use client";

import { useEffect } from "react";

declare global {
  interface Window {
    instgrm?: { Embeds: { process: () => void } };
  }
}

const SCRIPT_SRC = "https://www.instagram.com/embed.js";
let scriptPromise: Promise<void> | null = null;

function loadEmbedScript(): Promise<void> {
  if (typeof window === "undefined") return Promise.resolve();
  if (window.instgrm) return Promise.resolve();
  if (!scriptPromise) {
    scriptPromise = new Promise((resolve, reject) => {
      const existing = document.querySelector<HTMLScriptElement>(`script[src="${SCRIPT_SRC}"]`);
      if (existing) {
        existing.addEventListener("load", () => resolve(), { once: true });
        existing.addEventListener("error", () => reject(new Error("embed.js failed")), { once: true });
        return;
      }
      const s = document.createElement("script");
      s.src = SCRIPT_SRC;
      s.async = true;
      s.onload = () => resolve();
      s.onerror = () => {
        scriptPromise = null;
        reject(new Error("embed.js failed"));
      };
      document.body.appendChild(s);
    });
  }
  return scriptPromise;
}

/** Official Instagram blockquote embed. Falls back to a plain link while embed.js loads or if it is blocked. */
export default function InstagramEmbed({ url }: { url: string }) {
  useEffect(() => {
    let cancelled = false;
    loadEmbedScript()
      .then(() => {
        if (!cancelled) window.instgrm?.Embeds.process();
      })
      .catch(() => {
        /* fallback link remains visible */
      });
    return () => {
      cancelled = true;
    };
  }, [url]);

  return (
    <div className="relative w-full overflow-hidden">
      <blockquote
        className="instagram-media"
        data-instgrm-permalink={url}
        data-instgrm-version="14"
        style={{
          background: "var(--bg-elev)",
          border: "1px solid var(--line)",
          borderRadius: 12,
          padding: 0,
          width: "100%",
        }}
      >
        <a href={url} target="_blank" rel="noreferrer" className="block p-6 text-center text-sm font-medium underline">
          View this reel on Instagram
        </a>
      </blockquote>
    </div>
  );
}
