// CloudFront Function (viewer-request) for a Next.js static export:
//   /            -> /index.html   (handled by default_root_object)
//   /about/      -> /about/index.html
//   /about       -> /about.html
//   /b/slug      -> /b/slug.html
// Paths that already have an extension (/_next/..., /favicon.ico) pass through.
function handler(event) {
  var request = event.request;
  var uri = request.uri;
  if (uri.endsWith('/')) {
    request.uri = uri + 'index.html';
  } else if (!uri.includes('.')) {
    request.uri = uri + '.html';
  }
  return request;
}
