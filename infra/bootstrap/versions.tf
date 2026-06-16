# Provider and Terraform version pinning for the bootstrap stack.
# PIN: local Terraform v1.14.9; azurerm 4.x (storage_container uses storage_account_id).
# Source: https://github.com/hashicorp/terraform-provider-azurerm/blob/main/website/docs/r/storage_container.html.markdown
terraform {
  required_version = ">= 1.9"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
    # azuread provisions the GitHub Actions OIDC deploy identity (Task 29):
    # app registration + federated credential + service principal. PIN ~> 3.0
    # (v3 uses application_id, not application_object_id, on the federated cred).
    # Source: https://github.com/hashicorp/terraform-provider-azuread/blob/main/docs/resources/application_federated_identity_credential.md
    azuread = {
      source  = "hashicorp/azuread"
      version = "~> 3.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.0"
    }
  }

  # Bootstrap uses a LOCAL backend by design: it creates the remote-state
  # storage the application stack will use (chicken-and-egg). Commit the
  # resulting terraform.tfstate or keep it with the operator — it contains
  # no application secrets, only the state-storage resource IDs.
}

# subscription_id is supplied via the ARM_SUBSCRIPTION_ID environment variable
# (required by azurerm v4). `terraform validate` does not need it; `apply` does.
# storage_use_azuread: the state storage account disables shared keys
# (shared_access_key_enabled = false), so the provider must use Azure AD for
# blob data-plane calls (e.g. post-create polling, container creation) — without
# this, apply fails with 403 KeyBasedAuthenticationNotPermitted.
provider "azurerm" {
  features {}
  storage_use_azuread = true
}

# Authenticates with the operator's `az login` identity (Azure CLI auth), same
# as azurerm. Creating the deploy app registration + role assignments needs
# Application Administrator (or Owner) + role-assignment write in the tenant.
provider "azuread" {}
