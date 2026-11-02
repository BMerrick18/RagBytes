locals {
  # /api/health returns 503 when the UI is up but its API is not, so one check covers both.
  health_checks = {
    prod     = "https://${var.domain}/api/health"
    dev      = "https://${cloudflare_dns_record.dev.name}/api/health"
    prod-api = "https://${cloudflare_dns_record.api["prod"].name}/health"
    dev-api  = "https://${cloudflare_dns_record.api["dev"].name}/health"
  }
  # The longest period DigitalOcean allows.
  alert_period = "1h"
}

resource "digitalocean_uptime_check" "health" {
  for_each = local.health_checks

  name    = "ragbyte-${each.key}"
  target  = each.value
  type    = "https"
  regions = ["eu_west", "us_east"]
  enabled = true
}

resource "digitalocean_uptime_alert" "down" {
  for_each = local.health_checks

  name       = "ragbyte-${each.key} is down"
  check_id   = digitalocean_uptime_check.health[each.key].id
  type       = "down"
  threshold  = 1
  comparison = "less_than"
  period     = local.alert_period

  notifications {
    email = var.alert_emails
  }
}

resource "digitalocean_uptime_alert" "prod_slow" {
  name       = "ragbyte-prod is slow"
  check_id   = digitalocean_uptime_check.health["prod"].id
  type       = "latency"
  threshold  = 2000
  comparison = "greater_than"
  period     = local.alert_period

  notifications {
    email = var.alert_emails
  }
}

locals {
  droplet_alerts = {
    cpu    = { type = "v1/insights/droplet/cpu", value = 90, window = "1h", what = "CPU" }
    memory = { type = "v1/insights/droplet/memory_utilization_percent", value = 90, window = "30m", what = "Memory" }
    disk   = { type = "v1/insights/droplet/disk_utilization_percent", value = 85, window = "30m", what = "Disk" }
  }
}

resource "digitalocean_monitor_alert" "droplet" {
  for_each = local.droplet_alerts

  description = "ragbyte Droplet: ${each.value.what} above ${each.value.value}% for ${each.value.window}"
  type        = each.value.type
  compare     = "GreaterThan"
  value       = each.value.value
  window      = each.value.window
  entities    = [digitalocean_droplet.ragbyte.id]
  enabled     = true

  alerts {
    email = var.alert_emails
  }
}
