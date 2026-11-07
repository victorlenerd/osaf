// CloudFront Function (viewer-request) for a Next.js static export plus the backend-rendered
// pages (backend/app/seo):
//   /                 -> /index.html          (handled by default_root_object)
//   /about/           -> /about/index.html
//   /about            -> /about.html
//   /b/slug           -> /b/slug.html         (business page written by the backend)
//   /places/ng/lagos  -> /places/ng/lagos.html
//   /b/slug/, /places/ng/ -> 301 without the trailing slash (one canonical URL per page)
// Paths that already have an extension (/_next/..., /favicon.ico, /b/slug.md, /sitemap.xml)
// pass through.
function handler(event) {
  var request = event.request;
  var uri = request.uri;
  if (uri.length > 1 && uri.endsWith('/') && (uri.startsWith('/b/') || uri.startsWith('/places'))) {
    return {
      statusCode: 301,
      statusDescription: 'Moved Permanently',
      headers: { location: { value: uri.slice(0, -1) } },
    };
  }
  if (uri.endsWith('/')) {
    request.uri = uri + 'index.html';
  } else if (!uri.includes('.')) {
    request.uri = uri + '.html';
  }
  return request;
}
