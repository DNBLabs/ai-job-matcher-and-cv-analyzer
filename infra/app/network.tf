# VNet with three subnets and the private DNS zones that make Postgres, Blob,
# and Key Vault reachable only over the Azure backbone (CONTEXT.md §Network).
#
#   snet-aca       /23  Container Apps Environment infrastructure subnet
#                       (Consumption profile requires /23). Service endpoints
#                       for Storage + Key Vault so the env can reach them.
#   snet-pe        /27  Private endpoints (Blob).
#   snet-postgres  /27  Delegated to Postgres Flexible Server (VNet injection).

resource "azurerm_virtual_network" "main" {
  name                = "vnet-${local.name_prefix}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  address_space       = [var.vnet_address_space]
  tags                = local.common_tags
}

resource "azurerm_subnet" "aca" {
  name                 = "snet-aca"
  resource_group_name  = azurerm_resource_group.main.name
  virtual_network_name = azurerm_virtual_network.main.name
  address_prefixes     = [cidrsubnet(var.vnet_address_space, 7, 0)] # 10.20.0.0/23

  # Service endpoints let the ACA subnet reach Key Vault and Storage over the
  # backbone; Key Vault is locked to this subnet via network ACLs (keyvault.tf).
  service_endpoints = ["Microsoft.KeyVault", "Microsoft.Storage"]

  # A VNet-integrated Container App Environment requires its infrastructure
  # subnet to be delegated to Microsoft.App/environments.
  # Source: https://learn.microsoft.com/en-us/azure/container-apps/networking
  delegation {
    name = "aca-delegation"
    service_delegation {
      name    = "Microsoft.App/environments"
      actions = ["Microsoft.Network/virtualNetworks/subnets/join/action"]
    }
  }
}

resource "azurerm_subnet" "private_endpoints" {
  name                 = "snet-pe"
  resource_group_name  = azurerm_resource_group.main.name
  virtual_network_name = azurerm_virtual_network.main.name
  address_prefixes     = [cidrsubnet(var.vnet_address_space, 11, 32)] # 10.20.2.0/27
}

resource "azurerm_subnet" "postgres" {
  name                 = "snet-postgres"
  resource_group_name  = azurerm_resource_group.main.name
  virtual_network_name = azurerm_virtual_network.main.name
  address_prefixes     = [cidrsubnet(var.vnet_address_space, 11, 36)] # 10.20.2.128/27

  # Flexible Server is injected into a delegated subnet (private access mode).
  # Source: https://github.com/hashicorp/terraform-provider-azurerm/blob/main/website/docs/r/postgresql_flexible_server.html.markdown
  delegation {
    name = "fs-delegation"
    service_delegation {
      name = "Microsoft.DBforPostgreSQL/flexibleServers"
      actions = [
        "Microsoft.Network/virtualNetworks/subnets/join/action",
      ]
    }
  }
}

# ---- Private DNS zones -------------------------------------------------------
# Blob no longer uses a private endpoint (service endpoint + ACL instead; see
# storage.tf / ADR-0007), so no privatelink.blob DNS zone is needed.

# Postgres Flexible Server private DNS (zone name must end with this suffix).
resource "azurerm_private_dns_zone" "postgres" {
  name                = "${local.postgres_name}.private.postgres.database.azure.com"
  resource_group_name = azurerm_resource_group.main.name
  tags                = local.common_tags
}

resource "azurerm_private_dns_zone_virtual_network_link" "postgres" {
  name                  = "postgres-link"
  resource_group_name   = azurerm_resource_group.main.name
  private_dns_zone_name = azurerm_private_dns_zone.postgres.name
  virtual_network_id    = azurerm_virtual_network.main.id
  tags                  = local.common_tags
}
