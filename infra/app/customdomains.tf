# Custom domains for ADR-0011: www.getmeajob.dnblabs.co.uk (SWA) and
# api.getmeajob.dnblabs.co.uk (ACA). Cloudflare proxy disabled (proxied = false)
# on both records — ACA managed cert provisioning requires the CNAME to resolve
# directly to the Azure FQDN, not through Cloudflare's proxy.

# ---- Cloudflare DNS records (v5: cloudflare_dns_record, ttl required) -------

resource "cloudflare_dns_record" "frontend_cname" {
  zone_id = var.cloudflare_zone_id
  name    = var.frontend_custom_domain
  type    = "CNAME"
  content = azurerm_static_web_app.frontend.default_host_name
  proxied = false
  ttl     = 3600
}

resource "cloudflare_dns_record" "api_cname" {
  zone_id = var.cloudflare_zone_id
  name    = var.api_custom_domain
  type    = "CNAME"
  content = azurerm_container_app.api.ingress[0].fqdn
  proxied = false
  ttl     = 3600
}

# ---- SWA custom domain (cname-delegation: CNAME already points at SWA) -----

resource "azurerm_static_web_app_custom_domain" "frontend" {
  static_web_app_id = azurerm_static_web_app.frontend.id
  domain_name       = var.frontend_custom_domain
  validation_type   = "cname-delegation"

  depends_on = [cloudflare_dns_record.frontend_cname]
}

# ---- ACA custom domain with Azure-managed cert (async provisioning) ---------
# Omit certificate_binding_type + container_app_environment_certificate_id so
# Azure auto-provisions the managed cert. lifecycle.ignore_changes prevents
# Terraform from cycling on the async cert state after provisioning completes.

resource "azurerm_container_app_custom_domain" "api" {
  name             = var.api_custom_domain
  container_app_id = azurerm_container_app.api.id

  lifecycle {
    ignore_changes = [certificate_binding_type, container_app_environment_certificate_id]
  }

  depends_on = [cloudflare_dns_record.api_cname]
}
