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

# Azure requires this TXT record at asuid.<subdomain> to prove domain ownership
# before it will register the custom domain on the Container App. The value is
# the Container App Environment's customDomainVerificationId.
resource "cloudflare_dns_record" "api_domain_verification" {
  zone_id = var.cloudflare_zone_id
  name    = "asuid.${var.api_custom_domain}"
  type    = "TXT"
  content = azurerm_container_app_environment.main.custom_domain_verification_id
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
# lifecycle.ignore_changes prevents Terraform from reverting the cert binding
# that is applied by the terraform_data.api_managed_cert provisioner below.

resource "azurerm_container_app_custom_domain" "api" {
  name             = var.api_custom_domain
  container_app_id = azurerm_container_app.api.id

  lifecycle {
    ignore_changes = [certificate_binding_type, container_app_environment_certificate_id]
  }

  depends_on = [cloudflare_dns_record.api_cname, cloudflare_dns_record.api_domain_verification]
}

# The azurerm provider does not support Azure free managed certificates natively.
# This provisioner uses the Azure CLI (available on the GitHub Actions runner) to:
#   1. Create the managed certificate in the Container App Environment (idempotent)
#   2. Wait for provisioning to complete (up to 15 minutes)
#   3. Bind the cert to the custom domain (idempotent)
# triggers_replace = hostname + env id ensures this only re-runs if the domain or
# environment changes, not on every apply.
resource "terraform_data" "api_managed_cert" {
  triggers_replace = {
    hostname = var.api_custom_domain
    env_id   = azurerm_container_app_environment.main.id
  }

  provisioner "local-exec" {
    interpreter = ["bash", "-c"]
    command     = <<-EOT
      set -e
      ENV_NAME="${azurerm_container_app_environment.main.name}"
      RG="${azurerm_resource_group.main.name}"
      HOSTNAME="${var.api_custom_domain}"
      CERT_NAME="api-getmeajob-managed-cert"
      APP_NAME="${azurerm_container_app.api.name}"

      EXISTING=$(az containerapp env certificate list \
        --name "$ENV_NAME" --resource-group "$RG" \
        --query "[?name=='$CERT_NAME'].id" -o tsv 2>/dev/null || true)

      if [ -z "$EXISTING" ]; then
        az containerapp env certificate create \
          --name "$ENV_NAME" --resource-group "$RG" \
          --certificate-name "$CERT_NAME" \
          --hostname "$HOSTNAME" --validation-method CNAME
        for i in $(seq 1 30); do
          STATE=$(az containerapp env certificate list \
            --name "$ENV_NAME" --resource-group "$RG" \
            --query "[?name=='$CERT_NAME'].properties.provisioningState" -o tsv)
          [ "$STATE" = "Succeeded" ] && break
          sleep 30
        done
        EXISTING=$(az containerapp env certificate list \
          --name "$ENV_NAME" --resource-group "$RG" \
          --query "[?name=='$CERT_NAME'].id" -o tsv)
      fi

      BINDING=$(az containerapp show \
        --name "$APP_NAME" --resource-group "$RG" \
        --query "properties.configuration.ingress.customDomains[?name=='$HOSTNAME'].bindingType" \
        -o tsv 2>/dev/null || true)

      if [ "$BINDING" != "SniEnabled" ]; then
        az containerapp hostname bind \
          --name "$APP_NAME" --resource-group "$RG" \
          --hostname "$HOSTNAME" --certificate "$EXISTING"
      fi
    EOT
  }

  depends_on = [azurerm_container_app_custom_domain.api]
}
