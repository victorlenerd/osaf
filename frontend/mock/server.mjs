// Tiny mock of the Afefehub API for local frontend development.
// Run: node mock/server.mjs   (listens on PORT, default 8000)
import { createServer } from "node:http";
import { businesses } from "./fixtures.mjs";

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

createServer((req, res) => {
  const url = new URL(req.url, `http://localhost:${PORT}`);
  if (req.method === "OPTIONS") return send(res, 204, {});

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

  if (url.pathname === "/health") return send(res, 200, { ok: true });
  send(res, 404, { detail: "not found" });
}).listen(PORT, () => {
  console.log(`Afefehub mock API listening on http://localhost:${PORT}`);
});
