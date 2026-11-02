# Infrastructure and releases

| Part | Where | Run by |
|---|---|---|
| Droplet, firewall, SSH key, Cloudflare DNS, SSL, rate limit and Web Analytics | `infra/terraform/` | You, from your machine |
| Tests, image builds, deploys | `.github/workflows/` | GitHub Actions |
| What runs on the server | `docker-compose.yml`, `deploy/` | The deploy job |

## Environments

| Environment | Website | API | Deployed when |
|---|---|---|---|
| `development` | <https://dev.ragbytes.com> | <https://api-dev.ragbytes.com> | Automatically, on every merge to `main` |
| `production` | <https://ragbytes.com> | <https://api.ragbytes.com> | Only when someone clicks **Run workflow** on *Deploy to production* |

Each API serves Swagger UI at `/docs`, ReDoc at `/redoc` and the OpenAPI spec at `/openapi.json`.

Both run on the same Droplet; see [deploy/README.md](../deploy/README.md) for the layout.

## Workflows

| Workflow | Trigger | What it does |
|---|---|---|
| `ci.yml` (*CI*) | Pull request | API tests, web lint and build, test-build both images |
| `ci.yml` (*CI*) | Merge (push) to `main` | The same, then push images to GHCR and deploy them to dev |
| `deploy-prod.yml` (*Deploy to production*) | Run workflow button, from `main` | Deploy an existing build to prod |
| `deploy.yml` (*Deploy steps*) | Called by the two above, never on its own | The deploy steps shared by dev and prod; its runs appear inside CI and Deploy to production as *Release dev* / *Release prod* |

Images are tagged with the full commit SHA and `latest`:
`ghcr.io/bmerrick18/shark-byte-api` and `ghcr.io/bmerrick18/shark-byte-web`. Prod never builds
anything: it releases the exact images CI built for that commit, the same ones dev is running.

### Deploying to production

Actions → **Deploy to production** → **Run workflow**, with the branch set to `main`:

- Leave `image_tag` empty to deploy the latest commit on `main`. If CI for that commit hasn't
  finished building its images yet, the run stops with a message saying so.
- Or enter the full SHA of an earlier `main` commit to roll back to it.

### What a deploy does

1. Checks both images for the SHA exist in GHCR.
2. Adds the runner's IP to the `ragbyte` DigitalOcean firewall for SSH.
3. Copies `docker-compose.yml` to `/opt/ragbyte/<stack>/`, `deploy/edge/` to `/opt/ragbyte/edge/`
   and `deploy/release.sh` to `/opt/ragbyte/`, all from the commit being deployed.
4. Runs `release.sh`, which logs in to GHCR with the job's short-lived token, makes sure Caddy is
   running and reloads its config, pins `IMAGE_TAG` and `PUBLIC_API_URL` in the stack's `.env`,
   pulls, restarts and logs out again.
5. Checks the site's home page, `/docs` and a real `/api/chunks` upload, then the API's `/health`
   version, `/openapi.json`, Swagger UI and a real `/v1/chunk/structured` upload.
6. Removes the firewall rule, even if an earlier step failed.

### GitHub settings it needs

Repository-level, so both environments can use them (Settings → Secrets and variables → Actions):

| Name | Kind | Value |
|---|---|---|
| `DIGITALOCEAN_TOKEN` | Secret | DigitalOcean token with custom scopes `firewall:read` and `firewall:update` only |
| `DEPLOY_SSH_KEY` | Secret | Private key whose public half is in `/root/.ssh/authorized_keys` on the Droplet |
| `DEPLOY_HOST` | Secret | Droplet IP (`terraform output droplet_ip`) |
| `DEPLOY_KNOWN_HOSTS` | Secret | `<ip> ssh-ed25519 AAAA...`, from `/etc/ssh/ssh_host_ed25519_key.pub` on the Droplet |

The host and known-hosts entries are secrets rather than variables so the Droplet's IP is masked
in workflow logs, which are public if the repository is.

The `development` and `production` environments are created by the first run that uses them.
To also require an approval click before prod, add a required reviewer to `production`.

## Monitoring

`GET /api/health` on either site reports which commit its UI and API were built from:

```json
{ "status": "ok", "web": "<sha>", "api": "<sha>" }
```

It returns 503 with `"status": "degraded"` when the UI is up but can't reach its API. Every deploy
checks that both values match the SHA it just released.

Terraform (`infra/terraform/monitoring.tf`) sets up email alerts to `alert_emails`:

| Alert | Fires when |
|---|---|
| `ragbyte-prod is down` | `https://ragbytes.com/api/health` fails for 1 hour |
| `ragbyte-dev is down` | `https://dev.ragbytes.com/api/health` fails for 1 hour |
| `ragbyte-prod-api is down` | `https://api.ragbytes.com/health` fails for 1 hour |
| `ragbyte-dev-api is down` | `https://api-dev.ragbytes.com/health` fails for 1 hour |
| `ragbyte-prod is slow` | Prod health takes over 2 seconds for 1 hour |
| Droplet CPU / memory / disk | Above 90% / 90% / 85% for 1 hour / 30 minutes / 30 minutes |

An hour is the longest an uptime alert can wait. For a quicker look, the check's history is in the
control panel.

The checks run from London-adjacent `eu_west` and from `us_east`. Results and history are in the
DigitalOcean control panel under **Monitoring → Uptime** and on the Droplet's **Graphs** tab.

Visitor numbers are in Cloudflare under **Analytics & Logs → Web Analytics**. Cloudflare adds its
cookie-free beacon to pages as they pass through, so there's no snippet in the app.

## Terraform

State is kept locally in `infra/terraform/terraform.tfstate` (git-ignored). Back it up; if you
start running Terraform from more than one machine, move it to a remote backend first.

```powershell
cd infra/terraform
copy terraform.tfvars.example terraform.tfvars   # then set admin_cidrs to your IP
$env:DIGITALOCEAN_TOKEN = "<full-access DigitalOcean token>"
$env:CLOUDFLARE_API_TOKEN = "<token: Zone Read, DNS Edit, Zone Settings Edit, Zone WAF Edit on the zone, and Account Analytics Edit>"
terraform init
terraform plan
terraform apply
```

The Droplet has `prevent_destroy` set, and changes to its image or SSH keys are ignored, so a plan
can never rebuild it by accident.

The firewall's HTTP and HTTPS sources come from Cloudflare's published IP ranges, so re-running
`terraform apply` picks up any changes Cloudflare makes to them.

If your home IP changes and SSH stops working, update `admin_cidrs` and run `terraform apply`.

## Not managed here

- The Cloudflare Origin Certificate and key, kept in `/etc/ragbyte/certs` on the Droplet. Creating
  them with Terraform would put the private key in the state file.
- `/opt/ragbyte/edge/.env` on the Droplet (the four domain settings and `CERTS_DIR`).
- Docker itself and swap, installed once as described in [deploy/README.md](../deploy/README.md).
