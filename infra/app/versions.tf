# Application stack: ACA, Postgres, Service Bus, Blob, Key Vault, ACR (Task 26).
# PIN: Terraform >= 1.9 (local v1.14.9); azurerm ~> 4.0 (matches bootstrap lock).
# Source: https://github.com/hashicorp/terraform-provider-azurerm/blob/main/website/docs/r/container_app.html.markdown
terraform {
  required_version = ">= 1.9"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.0"
    }
  }

  # PARTIAL backend: the remote-state storage account name carries a random
  # suffix only known after the bootstrap stack (Task 25) is applied, so it is
  # supplied at init time, not committed here:
  #
  #   terraform init \
  #     -backend-config="storage_account_name=$(cd ../bootstrap && terraform output -raw storage_account_name)"
  #
  # CI runs `terraform init -backend=false` and never touches remote state.
  backend "azurerm" {
    resource_group_name = "rg-ai-job-matcher-tfstate"
    container_name      = "tfstate"
    key                 = "app.tfstate"
    use_azuread_auth    = true
  }
}

# subscription_id comes from the ARM_SUBSCRIPTION_ID environment variable
# (required by azurerm v4). `terraform validate` does not need it; `apply` does.
provider "azurerm" {
  features {
    key_vault {
      # Recover soft-deleted vaults on apply rather than failing; purge
      # protection still blocks accidental permanent deletion.
      purge_soft_delete_on_destroy    = false
      recover_soft_deleted_key_vaults = true
    }
  }
  # Blob storage disables shared keys (storage.tf), so the provider must use
  # Azure AD for blob data-plane calls (post-create poll, container management).
  storage_use_azuread = true
}

provider "random" {}
