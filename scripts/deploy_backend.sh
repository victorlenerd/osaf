#!/usr/bin/env bash
# Build the backend image for Fargate (linux/amd64), push to ECR, and roll the ECS service.
# Usage: AWS_PROFILE=prod scripts/deploy_backend.sh [tag]
set -euo pipefail
cd "$(dirname "$0")/.."

TAG="${1:-$(git rev-parse --short HEAD)}"
REGION="${AWS_REGION:-us-east-1}"
TF_DIR=infra/terraform

out() { terraform -chdir="$TF_DIR" output -raw "$1"; }
REPO="$(out ecr_repository_url)"
SVC="$(out ecs_service)"            # "<cluster>/<service>"
CLUSTER="${SVC%%/*}"; SERVICE="${SVC##*/}"
ACCOUNT="${REPO%%.dkr.ecr*}"

echo "==> login to ECR ($REGION)"
aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin "${ACCOUNT}.dkr.ecr.${REGION}.amazonaws.com"

echo "==> build + push $REPO:$TAG"
docker buildx build --platform linux/amd64 -t "$REPO:$TAG" -t "$REPO:latest" --push backend

echo "==> roll service $SERVICE on $CLUSTER"
aws ecs update-service --region "$REGION" --cluster "$CLUSTER" --service "$SERVICE" --force-new-deployment --desired-count "${DESIRED_COUNT:-1}" --query 'service.deployments[0].{status:status,rollout:rolloutState}' --output table
echo "==> waiting for stable…"
aws ecs wait services-stable --region "$REGION" --cluster "$CLUSTER" --services "$SERVICE"
echo "done: https://api.afefehub.com/healthz"
