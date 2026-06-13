# Bootstrap stack: resource group + geo-redundant storage account + container
# that hold the Terraform remote state for the application stack (Task 26).
# Hardened because Terraform state contains secrets in plaintext.

locals {
  # FinOps-mandated tags applied to every resource (CONTEXT.md §Tagging).
  common_tags = {
    project       = var.project
    env           = var.environment
    owner         = var.owner_email
    "cost-center" = var.cost_center
  }
}

# Random suffix keeps the globally-scoped storage account name unique without
# requiring the operator to invent one. Persisted in state -> stable across applies.
# Source: https://github.com/hashicorp/terraform-provider-random/blob/main/website/docs/r/string.html.markdown
resource "random_string" "suffix" {
  length  = 6
  upper   = false
  special = false
  numeric = true
}

resource "azurerm_resource_group" "tfstate" {
  name     = var.resource_group_name
  location = var.location
  tags     = local.common_tags
}

# Geo-redundant (GRS) state storage. Public anonymous blob access disabled and
# shared access keys disabled -> remote backend must use Azure AD auth
# (use_azuread_auth = true). Versioning + soft delete protect against state loss.
# Source: https://github.com/hashicorp/terraform-provider-azurerm/blob/main/website/docs/r/storage_account.html.markdown
resource "azurerm_storage_account" "tfstate" {
  name                = "${var.state_storage_account_prefix}${random_string.suffix.result}"
  resource_group_name = azurerm_resource_group.tfstate.name
  location            = azurerm_resource_group.tfstate.location

  account_tier             = "Standard"
  account_replication_type = "GRS" # geo-redundant per Task 25 AC

  # Security hardening for a store of plaintext secrets.
  min_tls_version                   = "TLS1_2"
  allow_nested_items_to_be_public   = false
  shared_access_key_enabled         = false # AAD-auth only; no static keys
  infrastructure_encryption_enabled = true

  # public_network_access stays enabled: GitHub Actions runners and the operator
  # reach remote state over the public endpoint. Lock down with network rules later.
  public_network_access_enabled = true

  blob_properties {
    versioning_enabled = true

    delete_retention_policy {
      days = 7
    }

    container_delete_retention_policy {
      days = 7
    }
  }

  tags = local.common_tags
}

# Container for the application-stack state blob. azurerm v4 takes
# storage_account_id (storage_account_name is deprecated).
# Source: https://github.com/hashicorp/terraform-provider-azurerm/blob/main/website/docs/r/storage_container.html.markdown
resource "azurerm_storage_container" "tfstate" {
  name                  = var.state_container_name
  storage_account_id    = azurerm_storage_account.tfstate.id
  container_access_type = "private"
}
