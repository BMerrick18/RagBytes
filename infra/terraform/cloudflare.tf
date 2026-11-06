data "cloudflare_zone" "site" {
  filter = {
    name = var.domain
  }
}

locals {
  zone_id = data.cloudflare_zone.site.id
  # One level below the zone, so the free edge certificate and the *.ragbytes.com origin certificate cover them.
  api_hosts = {
    prod = var.api_subdomain
    dev  = "${var.api_subdomain}-${var.dev_subdomain}"
  }
}

resource "cloudflare_dns_record" "apex" {
  zone_id = local.zone_id
  name    = var.domain
  type    = "A"
  content = digitalocean_droplet.ragbyte.ipv4_address
  proxied = true
  ttl     = 1
}

resource "cloudflare_dns_record" "www" {
  zone_id = local.zone_id
  name    = "www.${var.domain}"
  type    = "CNAME"
  content = var.domain
  proxied = true
  ttl     = 1
}

resource "cloudflare_dns_record" "dev" {
  zone_id = local.zone_id
  name    = "${var.dev_subdomain}.${var.domain}"
  type    = "A"
  content = digitalocean_droplet.ragbyte.ipv4_address
  proxied = true
  ttl     = 1
}

resource "cloudflare_dns_record" "api" {
  for_each = local.api_hosts

  zone_id = local.zone_id
  name    = "${each.value}.${var.domain}"
  type    = "A"
  content = digitalocean_droplet.ragbyte.ipv4_address
  proxied = true
  ttl     = 1
}

# The Free plan allows one rule, a 10-second window, and matching on the path only. The website's
# upload route and every tier endpoint reach the same API, so they share the limit. Add new tiers here.
resource "cloudflare_ruleset" "rate_limit" {
  zone_id = local.zone_id
  name    = "RagBytes rate limits"
  kind    = "zone"
  phase   = "http_ratelimit"

  rules = [{
    description = "Chunking requests per address"
    expression  = "(http.request.uri.path in {\"/api/chunks\" \"/v1/chunk/basic\" \"/v1/chunk/structured\" \"/v1/chunk/semantic\"})"
    action      = "block"
    enabled     = true
    ratelimit = {
      characteristics     = ["cf.colo.id", "ip.src"]
      period              = 10
      requests_per_period = var.chunk_requests_per_10s
      mitigation_timeout  = 10
    }
  }]
}

resource "cloudflare_web_analytics_site" "site" {
  account_id   = data.cloudflare_zone.site.account.id
  zone_tag     = local.zone_id
  auto_install = true
}

resource "cloudflare_zone_setting" "ssl" {
  zone_id    = local.zone_id
  setting_id = "ssl"
  value      = "strict"
}

resource "cloudflare_zone_setting" "always_use_https" {
  zone_id    = local.zone_id
  setting_id = "always_use_https"
  value      = "on"
}
