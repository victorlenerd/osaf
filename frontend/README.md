# Afefehub web app

Public site for Afefehub: search businesses across Africa and read their video and voice reviews.
Next.js 15 (app router, static export), TypeScript, Tailwind CSS 4. All data is fetched
client-side from the Afefehub API; nothing is fetched at build time.

## Environment variables

Copy `.env.example` to `.env.local` and fill in:

| Variable | Default | Purpose |
| --- | --- | --- |
| `NEXT_PUBLIC_API_BASE` | `http://localhost:8000` | Base URL of the API, no trailing slash. Production: `https://api.afefehub.com`. |
| `NEXT_PUBLIC_WHATSAPP_NUMBER` | `+1 (555) 137-0042` | WhatsApp number reviewers send reel links to. Shown on the home page and used for the wa.me link. |
| `NEXT_PUBLIC_REPO_URL` | empty | Link to the public repository, shown on `/about` and in the footer. |

These are inlined at build time, so rebuild after changing them.

## Local development

```bash
pnpm install
```

Start the mock API (fixture data for four businesses, matches the real API contract):

```bash
pnpm mock
```

In another terminal start the dev server:

```bash
pnpm dev
```

Open http://localhost:3000. Try searching "jollof", "barber" or "coffee". The mock lives in
`mock/server.mjs` and `mock/fixtures.mjs`; it serves `GET /api/search` and `GET /api/business/{id}`
with CORS enabled and a small artificial delay so loading states are visible. It also serves
`GET /api/review/{id}/audio` for the one voice-note fixture (a bundled 6-second tone,
`mock/sample-voice.m4a`), with Range support like the real presigned S3 file.

## Lint and build

```bash
pnpm lint
```

```bash
pnpm build
```

`pnpm build` writes a static export to `out/` containing `index.html`, `business.html`,
`about.html` and `404.html` plus `_next/` assets. The business page reads `?id=` on the client,
so one `business.html` serves every business. The CloudFront function on the site distribution
maps extensionless paths (`/about`, `/business`) to the matching `.html` file.

## Deployment

Build with the production API base, then sync to the site bucket and invalidate CloudFront:

```bash
NEXT_PUBLIC_API_BASE=https://api.afefehub.com pnpm build
```

```bash
aws s3 sync out/ s3://afefehub-site-prod --delete
```

```bash
aws cloudfront create-invalidation --distribution-id <DISTRIBUTION_ID> --paths "/*"
```

## Project layout

- `app/` pages: `/` (search), `/business` (business page, client-side `useSearchParams` in a Suspense boundary), `/about`, `/terms`, `/privacy`, `not-found.tsx`
- `lib/legal.ts` entity name, address, contact mailboxes, governing law and effective dates used by the Terms and Privacy pages. Review before launch.
- `components/` header, footer, search box, result card, summary card, review card, Instagram embed, badges
- `lib/api.ts` typed fetchers, `lib/types.ts` API types, `lib/constants.ts` countries, categories, language names
- `mock/` local mock API

## Instagram embeds

Review cards render the official `blockquote.instagram-media` embed and load
`https://www.instagram.com/embed.js` once, then call `window.instgrm.Embeds.process()`.
A plain "Open on Instagram" link is always shown as a fallback. Embeds only resolve for real,
public reels, so the mock fixtures show the fallback box.
