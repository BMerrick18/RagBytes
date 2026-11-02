output "droplet_ip" {
  value = digitalocean_droplet.ragbyte.ipv4_address
}

output "firewall_name" {
  description = "Looked up by the deploy workflow to open SSH for its runner."
  value       = digitalocean_firewall.ragbyte.name
}

output "prod_url" {
  value = "https://${var.domain}"
}

output "dev_url" {
  value = "https://${cloudflare_dns_record.dev.name}"
}

output "api_urls" {
  value = { for stack, record in cloudflare_dns_record.api : stack => "https://${record.name}" }
}
