# One-time Microsoft Graph Mail.Send grant for the API + worker managed
# identities (Task 29 / ADR-0006). Kept in its own stack and state, applied
# ONCE by the operator with `az login` AFTER the app stack — deliberately NOT
# reconciled by the per-merge deploy pipeline, so the routine deploy identity
# never needs tenant-wide AppRoleAssignment.ReadWrite.All.
#
# PIN: Terraform >= 1.9 (local v1.14.9); azuread ~> 3.0; azurerm ~> 4.0 (data
# sources only). Local backend, like infra/bootstrap.
terraform {
  required_version = ">= 1.9"

  required_providers {
    azuread = {
      source  = "hashicorp/azuread"
      version = "~> 3.0"
    }
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
  }
}

# Both providers authenticate with the operator's `az login` identity, which
# must hold Application Administrator (Graph app-role assignment write) plus read
# on the application resource group. subscription_id comes from ARM_SUBSCRIPTION_ID.
provider "azurerm" {
  features {}
}

provider "azuread" {}
