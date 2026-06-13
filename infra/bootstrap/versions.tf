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
provider "azurerm" {
  features {}
}
