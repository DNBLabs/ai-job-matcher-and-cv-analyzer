# Outputs feed the application stack's remote backend configuration (Task 26).

output "resource_group_name" {
  description = "Resource group holding the remote-state storage account."
  value       = azurerm_resource_group.tfstate.name
}

output "storage_account_name" {
  description = "Storage account holding the remote state blob."
  value       = azurerm_storage_account.tfstate.name
}

output "container_name" {
  description = "Blob container holding the application-stack state."
  value       = azurerm_storage_container.tfstate.name
}

# ---- GitHub Actions OIDC deploy identity (Task 29) --------------------------
# Set these three as GitHub Actions repository secrets (no client secret exists):
#   AZURE_CLIENT_ID, AZURE_TENANT_ID, AZURE_SUBSCRIPTION_ID.

output "deploy_client_id" {
  description = "Client ID of the GitHub Actions OIDC deploy identity -> GitHub secret AZURE_CLIENT_ID."
  value       = azuread_application_registration.deploy.client_id
}

output "tenant_id" {
  description = "Entra tenant ID -> GitHub secret AZURE_TENANT_ID."
  value       = data.azurerm_subscription.current.tenant_id
}

output "subscription_id" {
  description = "Subscription ID -> GitHub secret AZURE_SUBSCRIPTION_ID."
  value       = data.azurerm_subscription.current.subscription_id
}

# Copy-paste backend block for the application stack (infra/app/backend.tf).
output "app_stack_backend_config" {
  description = "Backend block for the application stack. Uses Azure AD auth (no shared keys)."
  value       = <<-EOT
    terraform {
      backend "azurerm" {
        resource_group_name  = "${azurerm_resource_group.tfstate.name}"
        storage_account_name = "${azurerm_storage_account.tfstate.name}"
        container_name       = "${azurerm_storage_container.tfstate.name}"
        key                  = "app.tfstate"
        use_azuread_auth     = true
      }
    }
  EOT
}
