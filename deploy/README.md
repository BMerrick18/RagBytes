# Running RagBytes on the Droplet

One DigitalOcean Droplet behind Cloudflare runs two environments of the app, prod and dev, behind
a single Caddy proxy:

| Compose project | Containers | Serves | Reachable from |
|---|---|---|---|
| `ragbyte-edge` | `caddy` | HTTPS on ports 80/443 for every hostname | The internet (via Cloudflare) |
| `ragbyte-prod` | `api`, `web` | `ragbytes.com`, `www.ragbytes.com`, `api.ragbytes.com` | `caddy` only |
| `ragbyte-dev` | `api`, `web` | `dev.ragbytes.com`, `api-dev.ragbytes.com` (both sent with `X-Robots-Tag: noindex`) | `caddy` only |

Caddy reaches each stack by network aliases (`prod-web`, `prod-api`, `dev-web`, `dev-api`) on the
shared `ragbyte-edge` Docker network. Each UI talks to its own stack's API over that stack's
private network.

Releases are done by GitHub Actions and the Droplet, firewall and DNS are managed with Terraform;
see [infra/README.md](../infra/README.md). This page covers the one-time server setup that neither
of those does.

## Layout on the server

```
/etc/ragbyte/certs/        origin.pem, origin.key (Cloudflare Origin Certificate)
/opt/ragbyte/release.sh    copied by every deploy
/opt/ragbyte/edge/         compose.yml, Caddyfile (copied by deploys), .env (by hand)
/opt/ragbyte/prod/         docker-compose.yml (copied by deploys), .env
/opt/ragbyte/dev/          docker-compose.yml (copied by deploys), .env
```

Deploys rewrite `COMPOSE_PROJECT_NAME`, `STACK`, `IMAGE_TAG` and `PUBLIC_API_URL` in a stack's
`.env` and leave any other lines, such as `API_WORKERS` and `RAGBYTES_OPENAI_API_KEY`, alone.
Container logs rotate at 10 MB,
keeping three files per container.

Each stack's API keeps its running totals for `GET /v1/stats` (documents chunked, chunks returned)
in a SQLite file on the Docker volume `ragbyte-<stack>_stats`. It survives deploys and is the only
thing the stacks write to disk. Deleting the volume resets the counter to zero. Each deploy's smoke
test chunks two small files, so every deploy adds 2 to the documents count.

## One-time setup

### 1. Create the infrastructure

Run Terraform as described in [infra/README.md](../infra/README.md). It creates the Droplet
(Ubuntu 24.04, 2 GB), the firewall (SSH from your IP, 80/443 from Cloudflare only) and the DNS
records, and sets Cloudflare's SSL mode to Full (strict) with Always Use HTTPS.

### 2. Install Docker and add swap

```bash
ssh root@<droplet-ip>
curl -fsSL https://get.docker.com | sh
fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab
```

### 3. Install the Cloudflare Origin Certificate

In Cloudflare: **SSL/TLS → Origin Server → Create Certificate**, RSA, hostnames `ragbytes.com` and
`*.ragbytes.com` (the wildcard covers `www`, `dev`, `api` and `api-dev`, but not deeper names
such as `api.dev`), PEM format. The private key is only shown
once.

```bash
mkdir -p /etc/ragbyte/certs && chmod 700 /etc/ragbyte/certs
nano /etc/ragbyte/certs/origin.pem   # paste the "Origin Certificate" block
nano /etc/ragbyte/certs/origin.key   # paste the "Private Key" block
chmod 600 /etc/ragbyte/certs/origin.key
```

### 4. Write the settings files

```bash
mkdir -p /opt/ragbyte/edge /opt/ragbyte/prod /opt/ragbyte/dev
cat > /opt/ragbyte/edge/.env <<'EOF'
PROD_DOMAINS=ragbytes.com, www.ragbytes.com
DEV_DOMAIN=dev.ragbytes.com
PROD_API_DOMAIN=api.ragbytes.com
DEV_API_DOMAIN=api-dev.ragbytes.com
CERTS_DIR=/etc/ragbyte/certs
EOF
echo "API_WORKERS=2" > /opt/ragbyte/prod/.env
echo "RAGBYTES_OPENAI_API_KEY=" >> /opt/ragbyte/prod/.env
echo "API_WORKERS=1" > /opt/ragbyte/dev/.env
echo "RAGBYTES_OPENAI_API_KEY=" >> /opt/ragbyte/dev/.env
```

Semantic chunking is unpublished. `RAGBYTES_SEMANTIC_ENABLED` defaults to false, so
`POST /v1/chunk/semantic` is not served. To offer it again, set that to true and put the OpenAI key in
`RAGBYTES_OPENAI_API_KEY`. The key stays in that file. Requests do not carry one. The website also hides
the tier until it is marked listed and available in `web/src/lib/tiers.ts`.

### 5. Deploy

Merge to `main` (or re-run CI on `main`) to deploy dev, then run **Deploy to production** in the
Actions tab. The first deploy copies the Compose files and starts Caddy.

If Cloudflare shows error 526, the certificate files are wrong or the SSL mode is not Full
(strict); 521 means the containers are not running or the firewall is blocking Cloudflare; 502
means Caddy is up but that stack's `web` container isn't.

## Day-to-day

```bash
cd /opt/ragbyte/prod                  # or dev, or edge
docker compose ps
docker compose logs -f                # follow this stack's logs
docker compose logs -f api            # just the API
docker compose restart web            # restart one service
```

## Limits to know about

- **Request time:** Cloudflare closes a request after about 100 seconds (error 524). Very large
  PDFs that take longer to chunk will fail through the proxy, even though the API keeps working.
- **Upload size:** Caddy rejects bodies over 50 MB (`deploy/edge/Caddyfile`). Cloudflare's free
  plan caps uploads at 100 MB, so don't raise the Caddy limit beyond that.
- **Shared server:** dev and prod share the Droplet's 2 GB, so a runaway dev stack can slow prod.
  Edge changes (the Caddyfile) go live for both sites on whichever deploy runs next.
- **Abuse:** the sites and API are public with no keys. A Cloudflare rate limiting rule (managed
  in `infra/terraform/cloudflare.tf`) allows 10 chunking requests per 10 seconds per address across
  `/api/chunks` and the `/v1/chunk/<tier>` endpoints, then returns 429 for 10 seconds.

## Running it locally

With Docker Desktop running, from the repository root:

```bash
mkdir -p ~/ragbyte-test-certs
docker run --rm -v ~/ragbyte-test-certs:/certs alpine/openssl req -x509 -newkey rsa:2048 -nodes \
  -keyout /certs/origin.key -out /certs/origin.pem -days 1 -subj /CN=localhost
printf 'PROD_DOMAINS=localhost\nDEV_DOMAIN=dev.localhost\nPROD_API_DOMAIN=api.localhost\nDEV_API_DOMAIN=api-dev.localhost\nCERTS_DIR=%s\n' \
  ~/ragbyte-test-certs > deploy/edge/.env
docker compose -f deploy/edge/compose.yml up -d
printf 'COMPOSE_PROJECT_NAME=ragbyte-prod\nSTACK=prod\nPUBLIC_API_URL=https://api.localhost\n' > .env
docker compose up -d --build
```

Then open <https://localhost> and accept the certificate warning. Stop it with `docker compose down`
followed by `docker compose -f deploy/edge/compose.yml down`.
