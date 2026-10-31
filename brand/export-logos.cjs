// Renders the Afefehub mark and lockup to PNG at platform sizes.
//   cd brand && npm install && npm run export
const { Resvg } = require("@resvg/resvg-js");
const fs = require("fs");
const path = require("path");

const REPO = path.resolve(__dirname, "..");
const FRONTEND = path.join(REPO, "frontend");
const PUBLIC = path.join(FRONTEND, "public");
const BRAND = __dirname;
const FONT_DIR = path.join(__dirname, "fonts");

const YELLOW = "#ffc72c";
const INK = "#0a0a0a";
const INK_700 = "#2b2b2b";
const WHITE = "#ffffff";

const BUBBLE = "M18 6H46a12 12 0 0 1 12 12v20a12 12 0 0 1-12 12H26L12 60V49A12 12 0 0 1 6 38V18A12 12 0 0 1 18 6Z";
const LETTER_A = "M21 40 32 16l11 24M25.5 32.5h13";

// Mark in the 64x64 grid. variant: "ink" (dark bubble, yellow A) or "white" (white bubble, ink A).
function markGroup(variant = "ink") {
  const bubble = variant === "white" ? WHITE : "url(#g)";
  const letter = variant === "white" ? INK : YELLOW;
  return `<path d="${BUBBLE}" fill="${bubble}"/><path d="${LETTER_A}" fill="none" stroke="${letter}" stroke-width="5.5" stroke-linecap="round" stroke-linejoin="round"/>`;
}
const GRAD = `<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="${INK}"/><stop offset="1" stop-color="${INK_700}"/></linearGradient></defs>`;

// Square canvas of `size` px. The mark occupies `scale` of the canvas, centred. bg: colour or null.
function squareSvg({ size, scale = 1, bg = null, variant = "ink", radius = 0 }) {
  const m = size * scale;
  const off = (size - m) / 2;
  const bgRect = bg ? `<rect width="${size}" height="${size}" rx="${radius}" fill="${bg}"/>` : "";
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 ${size} ${size}">${GRAD}${bgRect}<g transform="translate(${off} ${off}) scale(${m / 64})">${markGroup(variant)}</g></svg>`;
}

// Horizontal lockup: mark + "Afefehub" wordmark. Natural grid 270x64, same as logo.svg.
function lockupSvg({ height, bg = null, variant = "ink", padX = 0, padY = 0 }) {
  const s = height / 64;
  const w = Math.round(270 * s + padX * 2);
  const h = Math.round(64 * s + padY * 2);
  const text = variant === "white" ? WHITE : INK;
  const bgRect = bg ? `<rect width="${w}" height="${h}" fill="${bg}"/>` : "";
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}">${GRAD}${bgRect}<g transform="translate(${padX} ${padY}) scale(${s})">${markGroup(variant)}<text x="74" y="45" font-family="Lato" font-size="38" font-weight="700" letter-spacing="-0.6" fill="${text}">Afefehub</text></g></svg>`;
}

// Open Graph card 1200x630: yellow field, lockup centred, tagline under it.
function ogSvg() {
  const W = 1200, H = 630;
  const s = 2.6; // lockup scale -> 702x166
  const lw = 270 * s, lh = 64 * s;
  const lx = (W - lw) / 2, ly = (H - lh) / 2 - 40;
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">${GRAD}<rect width="${W}" height="${H}" fill="${YELLOW}"/><g transform="translate(${lx} ${ly}) scale(${s})">${markGroup("ink")}<text x="74" y="45" font-family="Lato" font-size="38" font-weight="700" letter-spacing="-0.6" fill="${INK}">Afefehub</text></g><text x="${W / 2}" y="${ly + lh + 80}" text-anchor="middle" font-family="Lato" font-size="40" font-weight="700" fill="${INK_700}">Real reviews from real faces</text></svg>`;
}

function render(svg, outPath, width) {
  const r = new Resvg(svg, {
    fitTo: { mode: "width", value: width },
    font: { fontDirs: [FONT_DIR], loadSystemFonts: false, defaultFontFamily: "Lato" },
    shapeRendering: 2, textRendering: 2, imageRendering: 0,
  });
  const png = r.render().asPng();
  fs.mkdirSync(path.dirname(outPath), { recursive: true });
  fs.writeFileSync(outPath, png);
  console.log(path.relative(REPO, outPath).padEnd(52), `${r.width}x${r.height}`.padEnd(10), `${(png.length / 1024).toFixed(1)} KB`);
}

// Multi-size .ico: ICONDIR + PNG-encoded entries (supported by every modern browser and Windows 7+).
function writeIco(pngs, outPath) {
  const n = pngs.length;
  const header = Buffer.alloc(6);
  header.writeUInt16LE(0, 0); header.writeUInt16LE(1, 2); header.writeUInt16LE(n, 4);
  const dir = Buffer.alloc(16 * n);
  let offset = 6 + 16 * n;
  pngs.forEach(({ size, data }, i) => {
    const o = i * 16;
    dir.writeUInt8(size >= 256 ? 0 : size, o);
    dir.writeUInt8(size >= 256 ? 0 : size, o + 1);
    dir.writeUInt8(0, o + 2); dir.writeUInt8(0, o + 3);
    dir.writeUInt16LE(1, o + 4); dir.writeUInt16LE(32, o + 6);
    dir.writeUInt32LE(data.length, o + 8); dir.writeUInt32LE(offset, o + 12);
    offset += data.length;
  });
  fs.writeFileSync(outPath, Buffer.concat([header, dir, ...pngs.map((p) => p.data)]));
  console.log(path.relative(REPO, outPath).padEnd(52), pngs.map((p) => p.size).join("/").padEnd(10), `${(fs.statSync(outPath).size / 1024).toFixed(1)} KB`);
}

// ---------- Web: served from frontend/public ----------
for (const size of [16, 32, 48]) render(squareSvg({ size }), path.join(PUBLIC, `favicon-${size}.png`), size);
writeIco(
  [16, 32, 48].map((size) => ({ size, data: new Resvg(squareSvg({ size }), { fitTo: { mode: "width", value: size } }).render().asPng() })),
  path.join(PUBLIC, "favicon.ico"),
);
// iOS flattens alpha to black, so the touch icon gets the brand field behind the mark.
render(squareSvg({ size: 180, scale: 0.78, bg: YELLOW }), path.join(PUBLIC, "apple-touch-icon.png"), 180);
// Android / PWA: "any" icons keep transparency; "maskable" keeps the mark inside the 80% safe zone.
render(squareSvg({ size: 192 }), path.join(PUBLIC, "icon-192.png"), 192);
render(squareSvg({ size: 512 }), path.join(PUBLIC, "icon-512.png"), 512);
render(squareSvg({ size: 192, scale: 0.6, bg: YELLOW }), path.join(PUBLIC, "icon-192-maskable.png"), 192);
render(squareSvg({ size: 512, scale: 0.6, bg: YELLOW }), path.join(PUBLIC, "icon-512-maskable.png"), 512);
// Social preview card (Open Graph / X / WhatsApp / LinkedIn link previews).
render(ogSvg(), path.join(PUBLIC, "og-image.png"), 1200);

// ---------- Brand kit: not served, for profiles, stores and decks ----------
const mark = path.join(BRAND, "mark");
render(squareSvg({ size: 1024 }), path.join(mark, "afefehub-mark-1024.png"), 1024);
render(squareSvg({ size: 512 }), path.join(mark, "afefehub-mark-512.png"), 512);
render(squareSvg({ size: 256 }), path.join(mark, "afefehub-mark-256.png"), 256);
render(squareSvg({ size: 128 }), path.join(mark, "afefehub-mark-128.png"), 128);
render(squareSvg({ size: 512, variant: "white" }), path.join(mark, "afefehub-mark-512-on-dark.png"), 512);

const social = path.join(BRAND, "social");
// Square profile pictures on the yellow field; mark sized so circular crops keep it whole.
for (const size of [1080, 800, 720, 640, 400, 320, 300]) {
  render(squareSvg({ size, scale: 0.62, bg: YELLOW }), path.join(social, `afefehub-profile-${size}.png`), size);
}

const stores = path.join(BRAND, "app-icons");
// App Store: 1024 opaque (no alpha). Play Store: 512 with alpha allowed; Android adaptive uses the maskable safe zone.
render(squareSvg({ size: 1024, scale: 0.78, bg: YELLOW }), path.join(stores, "ios-app-icon-1024.png"), 1024);
render(squareSvg({ size: 512, scale: 0.78, bg: YELLOW, radius: 0 }), path.join(stores, "play-store-icon-512.png"), 512);
render(squareSvg({ size: 432, scale: 0.6, bg: YELLOW }), path.join(stores, "android-adaptive-foreground-432.png"), 432);

const lockup = path.join(BRAND, "lockup");
for (const h of [64, 128, 256, 512]) render(lockupSvg({ height: h }), path.join(lockup, `afefehub-lockup-${h}.png`), Math.round(270 * h / 64));
render(lockupSvg({ height: 256, variant: "white" }), path.join(lockup, "afefehub-lockup-256-on-dark.png"), Math.round(270 * 4));
render(lockupSvg({ height: 256, bg: YELLOW, padX: 96, padY: 64 }), path.join(lockup, "afefehub-lockup-256-yellow.png"), 1080 + 192);
