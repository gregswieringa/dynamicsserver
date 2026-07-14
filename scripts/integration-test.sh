#!/usr/bin/env bash
# Spins up a real Postgres + buyer-api via docker-compose.test.yml, waits for
# /health, runs the black-box integration suite in tests/integration/, and
# always tears the stack down on exit. Safe to run locally; the same script
# is what a Jenkins "post-deploy smoke test" stage would later call, pointed
# at whatever BASE_URL/DB_URL a real deploy uses instead of localhost.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

COMPOSE_PROJECT="buyerapi-it"
COMPOSE=(docker compose -p "$COMPOSE_PROJECT" -f docker-compose.test.yml)
BASE_URL="http://localhost:8001"
DB_URL="postgresql://buyer:buyer@localhost:5433/marketplace"

cleanup() {
  echo "--- tearing down test stack ---"
  "${COMPOSE[@]}" down -v
}
trap cleanup EXIT

echo "--- building and starting test stack ---"
"${COMPOSE[@]}" up -d --build

echo "--- waiting for buyer-api health check ---"
healthy=false
# 90 attempts, not 30: on a resource-constrained CI host (e.g. a small VM
# also running Jenkins itself), Postgres's initdb + schema load + buyer-api
# startup can genuinely take longer than 30s, especially right after a
# Docker build was competing for the same CPU. Hit this for real in CI.
for _ in $(seq 1 90); do
  if curl -sf "$BASE_URL/health" >/dev/null 2>&1; then
    healthy=true
    break
  fi
  sleep 1
done

if [ "$healthy" != true ]; then
  echo "buyer-api never became healthy" >&2
  "${COMPOSE[@]}" logs
  exit 1
fi

echo "--- running integration tests ---"
BUYER_API_BASE_URL="$BASE_URL" BUYER_API_TEST_DATABASE_URL="$DB_URL" \
  python3 -m pytest tests/integration -q "$@"
