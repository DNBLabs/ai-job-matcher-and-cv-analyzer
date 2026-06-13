# Naming, tags, resource group, and a stable random suffix shared by all
# globally-scoped resource names in this stack.

data "azurerm_client_config" "current" {}

resource "random_string" "suffix" {
  length  = 6
  upper   = false
  special = false
  numeric = true
}

locals {
  # FinOps-mandated tags applied to every resource (CONTEXT.md §Tagging).
  common_tags = {
    project       = var.project
    env           = var.environment
    owner         = var.owner_email
    "cost-center" = var.cost_center
  }

  suffix = random_string.suffix.result

  # Dash-style names (resource group, VNet, Container Apps, identities, etc.).
  name_prefix = "${var.project}-${var.environment}"

  # Compact names for resources that disallow dashes / cap length.
  storage_account_name = "st${var.name_token}${local.suffix}"   # <=24, lower alnum
  acr_name             = "acr${var.name_token}${local.suffix}"  # 5-50, alnum
  key_vault_name       = "kv-${var.name_token}-${local.suffix}" # <=24, alnum + dash
  servicebus_name      = "sb-${var.project}-${local.suffix}"
  postgres_name        = "psql-${var.project}-${local.suffix}"

  servicebus_queue_name = "analysis-runs"
  blob_container_name   = "cvs"
}

resource "azurerm_resource_group" "main" {
  name     = "rg-${local.name_prefix}"
  location = var.location
  tags     = local.common_tags
}
