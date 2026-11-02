variable "domain" {
  description = "Cloudflare zone the site is served from."
  type        = string
  default     = "ragbytes.com"
}

variable "dev_subdomain" {
  description = "Subdomain the dev stack is served from."
  type        = string
  default     = "dev"
}

variable "api_subdomain" {
  description = "Subdomain the prod API is served from. The dev API uses <api_subdomain>-<dev_subdomain>."
  type        = string
  default     = "api"
}

variable "chunk_requests_per_10s" {
  description = "Chunking requests one address may make in 10 seconds before Cloudflare returns 429 for 10 seconds."
  type        = number
  default     = 10
}

variable "region" {
  description = "DigitalOcean region slug."
  type        = string
  default     = "lon1"
}

variable "droplet_size" {
  description = "DigitalOcean Droplet size slug."
  type        = string
  default     = "s-1vcpu-2gb"
}

variable "admin_cidrs" {
  description = "Addresses allowed to SSH in permanently, e.g. your home IP as \"203.0.113.7/32\"."
  type        = list(string)
}

variable "alert_emails" {
  description = "Where uptime and Droplet alerts are emailed. Must be verified members of the DigitalOcean team."
  type        = list(string)
}

variable "admin_ssh_public_key_file" {
  description = "Public key installed for root on newly created Droplets."
  type        = string
  default     = "~/.ssh/ragbyte_do.pub"
}
