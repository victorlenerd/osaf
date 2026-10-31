// Tiny mock of the Afefehub API for local frontend development.
// Run: node mock/server.mjs   (listens on PORT, default 8000)
import { createServer } from "node:http";
import { createReadStream, statSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { businesses, googlePlaces, placeCandidates } from "./fixtures.mjs";

const SAMPLE_VOICE = join(dirname(fileURLToPath(import.meta.url)), "sample-voice.m4a");

const PORT = Number(process.env.PORT || 8000);

function toSearchResult(b) {
  const {
    business_id, name, formatted_address, city, country, category,
    review_count, recommend_rate, overall_sentiment, summary_headline, location,
  } = b.business;
  return {
    business_id, name, formatted_address, city, country, category,
    review_count, recommend_rate, overall_sentiment, summary_headline, location,
  };
}

function send(res, status, body) {
  res.writeHead(status, {
    "content-type": "application/json",
    "access-control-allow-origin": "*",
    "access-control-allow-headers": "*",
    "access-control-allow-methods": "GET, OPTIONS",
  });
  res.end(JSON.stringify(body));
}

function serveAudio(req, res, path) {
  const size = statSync(path).size;
  const headers = {
    "content-type": "audio/mp4",
    "accept-ranges": "bytes",
    "cache-control": "private, max-age=300",
    "access-control-allow-origin": "*",
    "access-control-allow-headers": "*",
    "access-control-allow-methods": "GET, HEAD, OPTIONS",
  };
  const range = /^bytes=(\d*)-(\d*)$/.exec(req.headers.range || "");
  let start = 0;
  let end = size - 1;
  if (range && (range[1] || range[2])) {
    if (range[1]) {
      start = Number(range[1]);
      if (range[2]) end = Math.min(Number(range[2]), size - 1);
    } else {
      start = Math.max(0, size - Number(range[2]));
    }
    if (start > end || start >= size) {
      res.writeHead(416, { ...headers, "content-range": `bytes */${size}` });
      return res.end();
    }
    res.writeHead(206, { ...headers, "content-range": `bytes ${start}-${end}/${size}`, "content-length": end - start + 1 });
  } else {
    res.writeHead(200, { ...headers, "content-length": size });
  }
  if (req.method === "HEAD") return res.end();
  createReadStream(path, { start, end }).pipe(res);
}

createServer((req, res) => {
  const url = new URL(req.url, `http://localhost:${PORT}`);
  if (req.method === "OPTIONS") return send(res, 204, {});

  // Voice-note audio. The real API 302-redirects to a presigned S3 URL; here we serve the
  // bundled sample directly, with Range support so the player can seek.
  const audio = url.pathname.match(/^\/api\/review\/([^/]+)\/audio$/);
  if (audio) {
    const id = decodeURIComponent(audio[1]);
    const hit = businesses.flatMap((b) => b.reviews).find((r) => r.review_id === id && r.source === "voice");
    if (!hit) return send(res, 404, { detail: "no audio for this review" });
    return serveAudio(req, res, SAMPLE_VOICE);
  }

  if (url.pathname === "/api/search") {
    const q = (url.searchParams.get("q") || "").trim().toLowerCase();
    const country = url.searchParams.get("country");
    const category = url.searchParams.get("category");
    const limit = Number(url.searchParams.get("limit") || 20);
    const results = businesses
      .filter((b) => {
        const biz = b.business;
        if (country && biz.country !== country) return false;
        if (category && biz.category !== category) return false;
        if (!q) return true;
        const hay = [biz.name, biz.formatted_address, biz.city, ...biz.keywords, biz.summary_headline || ""]
          .join(" ")
          .toLowerCase();
        return q.split(/\s+/).some((t) => hay.includes(t));
      })
      .slice(0, limit)
      .map(toSearchResult);
    // Simulate a little latency so loading states are visible
    return setTimeout(() => send(res, 200, { results }), 250);
  }

  const m = url.pathname.match(/^\/api\/business\/([^/]+)$/);
  if (m) {
    const hit = businesses.find((b) => b.business.business_id === decodeURIComponent(m[1]));
    if (!hit) return send(res, 404, { detail: "not found" });
    return setTimeout(() => send(res, 200, hit), 250);
  }

  // Google Places lookup: only called by the frontend when Afefehub search is empty.
  if (url.pathname === "/api/places/lookup") {
    const q = (url.searchParams.get("q") || "").trim().toLowerCase();
    const country = url.searchParams.get("country");
    const limit = Math.min(5, Math.max(1, Number(url.searchParams.get("limit") || 5)));
    if (q.length < 2) return send(res, 422, { detail: "q must be at least 2 characters" });
    if (q === "busy") return send(res, 429, { detail: "too many google lookups" });
    if (q === "nokey") return send(res, 503, { detail: "google lookup unavailable" });
    const candidates = placeCandidates
      .filter((c) => !country || c.country === country)
      .filter((c) => [c.name, c.formatted_address, c.city].join(" ").toLowerCase().includes(q))
      .slice(0, limit);
    return setTimeout(() => send(res, 200, { candidates }), 400);
  }

  // Live Google reviews + AI summary for a place id. afefe: ids and unknown ids → 404.
  const g = url.pathname.match(/^\/api\/places\/([^/]+)\/google$/);
  if (g) {
    const id = decodeURIComponent(g[1]);
    const hit = id.startsWith("afefe:") ? undefined : googlePlaces[id];
    if (!hit) return send(res, 404, { detail: "not found" });
    return setTimeout(() => send(res, 200, hit), 600);
  }

  if (url.pathname === "/health") return send(res, 200, { ok: true });
  send(res, 404, { detail: "not found" });
}).listen(PORT, () => {
  console.log(`Afefehub mock API listening on http://localhost:${PORT}`);
});
