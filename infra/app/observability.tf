# Log Analytics workspace backing the Container Apps Environment logs.
# PerGB2018 is the only generally-available SKU; 30-day retention keeps the
# log bill negligible at demo traffic (docs/finance/BUDGET.md).
resource "azurerm_log_analytics_workspace" "main" {
  name                = "log-${local.name_prefix}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  sku                 = "PerGB2018"
  retention_in_days   = 30
  tags                = local.common_tags
}
