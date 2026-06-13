# PostgreSQL Flexible Server — Burstable B1ms, the smallest viable prod SKU
# (docs/finance/BUDGET.md §SKU floor). VNet-injected via the delegated subnet
# with public access disabled (CONTEXT.md §Network: "no public endpoint").
#
# Auth: both password and Entra ID enabled. The app connects with the
# generated admin password (stored in Key Vault, consumed by the adapters in
# Task 27); Entra admin allows passwordless operator/break-glass access.

# Admin password generated in-stack. It lands in Terraform state, which is the
# accepted trade-off: state lives in the bootstrap GRS storage account with
# shared keys disabled and AAD-only access (CONTEXT.md §Secrets — no secrets in
# git/images; state itself is encrypted at rest and access-controlled).
resource "random_password" "postgres_admin" {
  length           = 32
  special          = true
  override_special = "!#$%&*()-_=+[]{}<>:?"
}

resource "azurerm_postgresql_flexible_server" "main" {
  name                = local.postgres_name
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location

  version  = var.postgres_version
  sku_name = "B_Standard_B1ms" # Burstable B1ms: 1 vCore, 2 GiB

  storage_mb        = 32768 # 32 GiB (BUDGET.md line item)
  auto_grow_enabled = true

  administrator_login    = var.postgres_administrator_login
  administrator_password = random_password.postgres_admin.result

  # Private access: injected into the delegated subnet, resolved by the private
  # DNS zone. public_network_access_enabled must be false in this mode.
  delegated_subnet_id           = azurerm_subnet.postgres.id
  private_dns_zone_id           = azurerm_private_dns_zone.postgres.id
  public_network_access_enabled = false

  authentication {
    active_directory_auth_enabled = true
    password_auth_enabled         = true
    tenant_id                     = data.azurerm_client_config.current.tenant_id
  }

  # The DNS zone vnet link must exist before the server is created so the
  # injected server name resolves.
  depends_on = [azurerm_private_dns_zone_virtual_network_link.postgres]

  tags = local.common_tags

  lifecycle {
    # Zone selection is non-deterministic on first apply; ignore drift so the
    # server is not recreated on later plans.
    ignore_changes = [zone]
  }
}

resource "azurerm_postgresql_flexible_server_database" "app" {
  name      = "jobmatcher"
  server_id = azurerm_postgresql_flexible_server.main.id
  charset   = "UTF8"
  collation = "en_US.utf8"
}
