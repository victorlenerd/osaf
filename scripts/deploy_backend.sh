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
# The ECR token goes into a throwaway Docker config instead of through `docker login`: the macOS
# keychain helper refuses to overwrite an existing registry entry ("The specified item already
# exists in the keychain", -25299), and the token only lasts 12 hours anyway. The engine the
# current context points at is kept, since a fresh config would forget it.
REGISTRY="${ACCOUNT}.dkr.ecr.${REGION}.amazonaws.com"
export DOCKER_HOST="${DOCKER_HOST:-$(docker context inspect --format '{{.Endpoints.docker.Host}}')}"
DOCKER_CONFIG="$(mktemp -d)"; export DOCKER_CONFIG
trap 'rm -rf "$DOCKER_CONFIG"' EXIT
[ -d "$HOME/.docker/cli-plugins" ] && ln -s "$HOME/.docker/cli-plugins" "$DOCKER_CONFIG/cli-plugins"
AUTH="$(printf 'AWS:%s' "$(aws ecr get-login-password --region "$REGION")" | base64 | tr -d '\n')"
(umask 077; printf '{"auths":{"%s":{"auth":"%s"}}}\n' "$REGISTRY" "$AUTH" > "$DOCKER_CONFIG/config.json")

echo "==> build + push $REPO:$TAG"
docker buildx build --platform linux/amd64 -t "$REPO:$TAG" -t "$REPO:latest" --push backend

echo "==> roll service $SERVICE on $CLUSTER"
aws ecs update-service --region "$REGION" --cluster "$CLUSTER" --service "$SERVICE" --force-new-deployment --desired-count "${DESIRED_COUNT:-1}" --query 'service.deployments[0].{status:status,rollout:rolloutState}' --output table
echo "==> waiting for stable…"
aws ecs wait services-stable --region "$REGION" --cluster "$CLUSTER" --services "$SERVICE"
echo "done: https://api.afefehub.com/healthz"
