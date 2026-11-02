#!/usr/bin/env bash
# Runs on the Droplet. Usage: release.sh <prod|dev> <image-tag> <registry-user> <public-api-url>,
# with a GHCR token on stdin.
# Expects /opt/ragbyte/<stack>/docker-compose.yml and /opt/ragbyte/edge/{compose.yml,Caddyfile,.env}.
set -euo pipefail

stack="$1"
tag="$2"
registry_user="$3"
api_url="$4"
case "$stack" in
  prod | dev) ;;
  *) echo "Unknown stack: $stack" >&2; exit 1 ;;
esac

root=/opt/ragbyte

docker login ghcr.io --username "$registry_user" --password-stdin
trap 'docker logout ghcr.io >/dev/null' EXIT

(
  cd "$root/edge"
  docker compose up -d
  docker compose exec -T caddy caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile
)

cd "$root/$stack"
touch .env
set_env() {
  sed -i "/^$1=/d" .env
  echo "$1=$2" >> .env
}
set_env COMPOSE_PROJECT_NAME "ragbyte-$stack"
set_env STACK "$stack"
set_env IMAGE_TAG "$tag"
set_env PUBLIC_API_URL "$api_url"

docker compose pull api web
docker compose up -d --remove-orphans
docker image prune -f
docker compose ps
