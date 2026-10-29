#!/usr/bin/env bash
# One-time: create the Terraform remote-state bucket, then run `terraform init`.
# Idempotent - safe to re-run.
set -euo pipefail

export AWS_PROFILE="${AWS_PROFILE:-prod}"
REGION="us-east-1"
EXPECTED_ACCOUNT="748201447723"
BUCKET="afefehub-tfstate-${EXPECTED_ACCOUNT}"

ACCOUNT="$(aws sts get-caller-identity --query Account --output text)"
if [[ "$ACCOUNT" != "$EXPECTED_ACCOUNT" ]]; then
  echo "AWS_PROFILE=$AWS_PROFILE is account $ACCOUNT, expected $EXPECTED_ACCOUNT" >&2
  exit 1
fi

if aws s3api head-bucket --bucket "$BUCKET" 2>/dev/null; then
  echo "state bucket s3://$BUCKET already exists"
else
  echo "creating s3://$BUCKET in $REGION"
  aws s3api create-bucket --bucket "$BUCKET" --region "$REGION"
fi

aws s3api put-bucket-versioning --bucket "$BUCKET" \
  --versioning-configuration Status=Enabled
aws s3api put-bucket-encryption --bucket "$BUCKET" \
  --server-side-encryption-configuration '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"},"BucketKeyEnabled":true}]}'
aws s3api put-public-access-block --bucket "$BUCKET" \
  --public-access-block-configuration BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
aws s3api put-bucket-ownership-controls --bucket "$BUCKET" \
  --ownership-controls 'Rules=[{ObjectOwnership=BucketOwnerEnforced}]'

echo "state bucket ready: s3://$BUCKET"
echo "next: cd $(dirname "$0") && terraform init"
