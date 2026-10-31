# Afefehub brand assets

Source of truth: `frontend/public/logo-mark.svg` (mark) and `frontend/public/logo.svg` (lockup).
Everything in this folder and the web icons in `frontend/public/` are rendered from those by
`export-logos.cjs`. Re-run it after changing the mark:

```bash
cd brand && npm install && npm run export
```

The wordmark is Lato Bold; `fonts/Lato-Bold.ttf` (SIL OFL) is bundled so renders don't depend on
system fonts.

Colours: ink `#0a0a0a` → `#2b2b2b` gradient bubble, yellow `#ffc72c` letter and brand field.

## Web (served from `frontend/public/`, referenced in `app/layout.tsx`)

| File | Size | Used for |
| --- | --- | --- |
| `favicon.svg` | vector | Browser tab icon (modern browsers) |
| `favicon.ico` | 16/32/48 | Legacy favicon, Windows pinned sites |
| `favicon-16.png`, `favicon-32.png`, `favicon-48.png` | 16, 32, 48 | PNG favicons |
| `apple-touch-icon.png` | 180 | iOS home screen (opaque yellow field; iOS rounds the corners) |
| `icon-192.png`, `icon-512.png` | 192, 512 | PWA / Android `purpose: any` (transparent) |
| `icon-192-maskable.png`, `icon-512-maskable.png` | 192, 512 | PWA / Android `purpose: maskable` (mark inside the 80% safe zone) |
| `og-image.png` | 1200×630 | Open Graph / X / WhatsApp / LinkedIn link previews |
| `site.webmanifest` | — | PWA manifest listing the icons above |

## `mark/` — standalone mark, transparent background

| File | Size | Used for |
| --- | --- | --- |
| `afefehub-mark-1024.png` | 1024 | Master raster, decks, print previews |
| `afefehub-mark-512.png` | 512 | General use, partner pages |
| `afefehub-mark-256.png`, `afefehub-mark-128.png` | 256, 128 | Email signatures, small placements |
| `afefehub-mark-512-on-dark.png` | 512 | White bubble + ink letter, for dark backgrounds |

## `social/` — square profile pictures on the yellow field

The mark fills 62% of the canvas so circular crops keep it whole.

| File | Size | Platform |
| --- | --- | --- |
| `afefehub-profile-1080.png` | 1080 | Instagram (upload size), TikTok |
| `afefehub-profile-800.png` | 800 | YouTube channel, Facebook page (min 170, 800 recommended) |
| `afefehub-profile-720.png` | 720 | Google Business Profile logo |
| `afefehub-profile-640.png` | 640 | WhatsApp Business profile photo |
| `afefehub-profile-400.png` | 400 | X / Twitter |
| `afefehub-profile-320.png` | 320 | Instagram display size |
| `afefehub-profile-300.png` | 300 | LinkedIn company logo |

## `app-icons/` — stores (for when there is a native app)

| File | Size | Platform |
| --- | --- | --- |
| `ios-app-icon-1024.png` | 1024 | App Store icon (opaque, no alpha, square; iOS masks it) |
| `play-store-icon-512.png` | 512 | Google Play listing icon |
| `android-adaptive-foreground-432.png` | 432 | Android adaptive icon foreground layer (mark in the 66 dp safe zone) |

## `lockup/` — mark + wordmark

| File | Size | Used for |
| --- | --- | --- |
| `afefehub-lockup-64.png` … `-512.png` | 270×64 to 2160×512 | Transparent, on light backgrounds; pick the height you need |
| `afefehub-lockup-256-on-dark.png` | 1080×256 | White version for dark backgrounds |
| `afefehub-lockup-256-yellow.png` | 1272×384 | On the brand field with padding, for covers and banners |
