# Azure Static Web App: the user-facing host for the built React/Vite SPA,
# separate from the API Container App (ADR-0008, Task 30). Free SKU = £0, within
# the £75/mo budget. The frontend is deployed to this resource out-of-band by the
# GitHub Actions SWA job (using api_key), NOT compiled into the API image.
#
# PIN: azurerm ~> 4.0. Required args name/location/resource_group_name; sku_tier /
# sku_size default "Free". Exports default_host_name + api_key (sensitive).
# Source: https://github.com/hashicorp/terraform-provider-azurerm/blob/main/website/docs/r/static_web_app.html.markdown

# Static Web Apps are only offered in a limited set of regions and NOT in
# uksouth (the rest of the stack's region). westeurope is the nearest supported
# location; the SPA is served from the global CDN edge regardless, so user
# latency is unaffected.
variable "static_web_app_location" {
  description = "Azure region for the Static Web App. Must be a SWA-supported region (uksouth is not); westeurope is the nearest."
  type        = string
  default     = "westeurope"
}

resource "azurerm_static_web_app" "frontend" {
  name                = "swa-${local.name_prefix}"
  resource_group_name = azurerm_resource_group.main.name
  location            = var.static_web_app_location

  sku_tier = "Free"
  sku_size = "Free"

  tags = local.common_tags
}
