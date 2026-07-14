#!/usr/bin/env bash
# Deploys built buyer-api/postgres images to staging or production on this
# host. Meant to run on the Oracle VM (Jenkins runs it directly -- Jenkins
# and both deploy targets live on the same VM, no SSH needed) -- it pulls
# ghcr.io/gregswieringa/buyer-api(-postgres):<tag> rather than building.
#
# Looks for deploy/<env>.env by default; set DEPLOY_ENV_DIR to look
# elsewhere (Jenkins points this at a persistent volume path outside its
# per-job workspace -- see docker-compose.jenkins.yml).
#
# Usage: ./scripts/deploy.sh <staging|prod> <image-tag>
set -euo pipefail

if [ $# -ne 2 ]; then
  echo "usage: $0 <staging|prod> <image-tag>" >&2
  exit 1
fi

ENVIRONMENT="$1"
IMAGE_TAG="$2"

case "$ENVIRONMENT" in
  staging|prod) ;;
  *)
    echo "environment must be 'staging' or 'prod', got '$ENVIRONMENT'" >&2
    exit 1
    ;;
esac

cd "$(dirname "${BASH_SOURCE[0]}")/.."

ENV_DIR="${DEPLOY_ENV_DIR:-deploy}"
ENV_FILE="${ENV_DIR}/${ENVIRONMENT}.env"
if [ ! -f "$ENV_FILE" ]; then
  echo "missing $ENV_FILE -- copy deploy/${ENVIRONMENT}.env.example there and fill in real secrets first" >&2
  exit 1
fi

COMPOSE=(docker compose -p "buyerapi-${ENVIRONMENT}" -f "docker-compose.${ENVIRONMENT}.yml" --env-file "$ENV_FILE")
BUYER_API_PORT="$(grep -E '^BUYER_API_PORT=' "$ENV_FILE" | cut -d= -f2)"

echo "--- deploying buyer-api:${IMAGE_TAG} to ${ENVIRONMENT} ---"
IMAGE_TAG="$IMAGE_TAG" "${COMPOSE[@]}" pull
IMAGE_TAG="$IMAGE_TAG" "${COMPOSE[@]}" up -d

echo "--- waiting for health check on port ${BUYER_API_PORT} ---"
healthy=false
for _ in $(seq 1 30); do
  if curl -sf "http://localhost:${BUYER_API_PORT}/health" >/dev/null 2>&1; then
    healthy=true
    break
  fi
  sleep 1
done

if [ "$healthy" != true ]; then
  echo "${ENVIRONMENT} did not become healthy after deploy" >&2
  IMAGE_TAG="$IMAGE_TAG" "${COMPOSE[@]}" logs --tail 100
  exit 1
fi

echo "${ENVIRONMENT} is healthy on buyer-api:${IMAGE_TAG}"
