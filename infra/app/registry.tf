# Container Registry holding SHA-tagged api + worker images (docs/finance/BUDGET.md: Basic).
# admin_user disabled -> pulls authenticate via the apps' managed identities
# (AcrPull role assignments in identity.tf), no static registry credentials.
resource "azurerm_container_registry" "main" {
  name                = local.acr_name
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  sku                 = "Basic"
  admin_enabled       = false
  tags                = local.common_tags
}
