resource "digitalocean_ssh_key" "admin" {
  name       = "ragbyte-droplet"
  public_key = trimspace(file(pathexpand(var.admin_ssh_public_key_file)))
}

resource "digitalocean_droplet" "ragbyte" {
  name       = "ragbyte"
  region     = var.region
  size       = var.droplet_size
  image      = "ubuntu-24-04-x64"
  ssh_keys   = [digitalocean_ssh_key.admin.id]
  monitoring = true
  tags       = ["ragbyte"]

  lifecycle {
    prevent_destroy = true
    # These only apply when a Droplet is first created; changing them would force a rebuild.
    ignore_changes = [image, ssh_keys, user_data]
  }
}

data "cloudflare_ip_ranges" "cloudflare" {}

resource "digitalocean_firewall" "ragbyte" {
  name        = "ragbyte"
  droplet_ids = [digitalocean_droplet.ragbyte.id]

  inbound_rule {
    protocol         = "tcp"
    port_range       = "22"
    source_addresses = var.admin_cidrs
  }

  dynamic "inbound_rule" {
    for_each = ["80", "443"]
    content {
      protocol   = "tcp"
      port_range = inbound_rule.value
      source_addresses = concat(
        data.cloudflare_ip_ranges.cloudflare.ipv4_cidrs,
        data.cloudflare_ip_ranges.cloudflare.ipv6_cidrs,
      )
    }
  }

  dynamic "outbound_rule" {
    for_each = ["tcp", "udp"]
    content {
      protocol              = outbound_rule.value
      port_range            = "all"
      destination_addresses = ["0.0.0.0/0", "::/0"]
    }
  }

  outbound_rule {
    protocol              = "icmp"
    destination_addresses = ["0.0.0.0/0", "::/0"]
  }
}
