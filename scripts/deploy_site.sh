#!/usr/bin/env bash
# Build the Next.js static export and publish it to the site bucket behind CloudFront.
# Usage: AWS_PROFILE=prod scripts/deploy_site.sh
#
# The bucket is shared: the backend (backend/app/seo) writes the crawlable business and hub
# pages, sitemaps and llms.txt into it. `--delete` would wipe those, so every backend-owned path
# is excluded here. Never deploy the site with a bare `aws s3 sync out/ ... --delete`.
set -euo pipefail
cd "$(dirname "$0")/.."

BUCKET="${SITE_BUCKET:-afefehub-site-prod}"
DIST="${CLOUDFRONT_DISTRIBUTION_ID:-E5F9GNTTG6KGL}"

# Keep in step with OWNED_PREFIXES and the files written in backend/app/seo/site.py.
BACKEND_OWNED=(
  "b/*"
  "places/*"
  "places.html"
  "places.md"
  "sitemap.xml"
  "sitemaps/*"
  "llms.txt"
  "llms-full.txt"
)
EXCLUDES=()
for p in "${BACKEND_OWNED[@]}"; do EXCLUDES+=(--exclude "$p"); done
# The IndexNow key file sits at the root as <hex key>.txt.
EXCLUDES+=(--exclude "[0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f]*.txt")

echo "==> build"
(cd frontend && NODE_ENV=production pnpm build)

for p in "${BACKEND_OWNED[@]}"; do
  if compgen -G "frontend/out/$p" > /dev/null; then
    echo "frontend/out/$p would shadow a backend-rendered page; rename the route" >&2
    exit 1
  fi
done

echo "==> sync to s3://$BUCKET (backend-owned pages excluded)"
aws s3 sync frontend/out/ "s3://$BUCKET" --delete "${EXCLUDES[@]}"

echo "==> invalidate CloudFront $DIST"
aws cloudfront create-invalidation --distribution-id "$DIST" --paths "/*" --query 'Invalidation.Id' --output text
echo "done: https://afefehub.com"
