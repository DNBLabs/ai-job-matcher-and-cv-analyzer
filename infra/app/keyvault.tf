# Key Vault for application secrets. RBAC authorization (no access policies);
# network locked to the ACA subnet (service endpoint) plus optional operator
# IPs for out-of-band secret management. CONTEXT.md §Network does not require a
# private endpoint for Key Vault, so a service-endpoint + deny-by-default ACL is
# used instead of a private endpoint (lighter, no extra DNS zone).
resource "azurerm_key_vault" "main" {
  name                = local.key_vault_name
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  tenant_id           = data.azurerm_client_config.current.tenant_id
  sku_name            = "standard"

  rbac_authorization_enabled = true # v4 arg name (was enable_rbac_authorization)
  purge_protection_enabled   = true
  soft_delete_retention_days = 7

  public_network_access_enabled = true # service-endpoint access; not a private endpoint

  network_acls {
    default_action             = "Deny"
    bypass                     = "AzureServices"
    virtual_network_subnet_ids = [azurerm_subnet.aca.id]
    ip_rules                   = var.operator_ip_rules
  }

  tags = local.common_tags
}

# The principal running `terraform apply` (operator locally or CI OIDC identity)
# needs data-plane rights to create/update secret values.
resource "azurerm_role_assignment" "deployer_secrets_officer" {
  scope                = azurerm_key_vault.main.id
  role_definition_name = "Key Vault Secrets Officer"
  principal_id         = data.azurerm_client_config.current.object_id
}

# ---- Secrets -----------------------------------------------------------------
# Real secret values are NOT committed. Placeholders are created so per-secret
# RBAC scopes exist (identity.tf); the operator sets real values out-of-band:
#   az keyvault secret set --vault-name <kv> --name openai-api-key --value <...>
# lifecycle ignore_changes keeps Terraform from reverting them.

locals {
  placeholder_secrets = {
    "google-oauth-client-id"     = "owner:api"
    "google-oauth-client-secret" = "owner:api"
    "openai-api-key"             = "owner:worker"
    "adzuna-app-id"              = "owner:worker"
    "adzuna-app-key"             = "owner:worker"
  }
}

resource "azurerm_key_vault_secret" "placeholders" {
  for_each = local.placeholder_secrets

  name         = each.key
  value        = "PLACEHOLDER-set-out-of-band"
  key_vault_id = azurerm_key_vault.main.id
  tags         = merge(local.common_tags, { consumer = each.value })

  depends_on = [azurerm_role_assignment.deployer_secrets_officer]

  lifecycle {
    ignore_changes = [value]
  }
}

# Database password is generated in-stack (database.tf), so Terraform owns its
# value — both the API and worker adapters read it (Task 27).
resource "azurerm_key_vault_secret" "database_password" {
  name         = "database-password"
  value        = random_password.postgres_admin.result
  key_vault_id = azurerm_key_vault.main.id
  tags         = merge(local.common_tags, { consumer = "api,worker" })

  depends_on = [azurerm_role_assignment.deployer_secrets_officer]
}
