# Outputs consumed by operators and the deploy workflow (Task 29).

output "resource_group_name" {
  description = "Application stack resource group."
  value       = azurerm_resource_group.main.name
}

output "acr_login_server" {
  description = "Container Registry login server for SHA-tagged image pushes."
  value       = azurerm_container_registry.main.login_server
}

output "api_fqdn" {
  description = "Public HTTPS FQDN of the API Container App (use for the OAuth callback URL)."
  value       = azurerm_container_app.api.ingress[0].fqdn
}

output "api_app_name" {
  description = "API Container App name (for `az containerapp update` revision pinning)."
  value       = azurerm_container_app.api.name
}

output "worker_app_name" {
  description = "Worker Container App name (for `az containerapp update` revision pinning)."
  value       = azurerm_container_app.worker.name
}

output "key_vault_name" {
  description = "Key Vault name for setting real secret values out-of-band."
  value       = azurerm_key_vault.main.name
}

output "postgres_fqdn" {
  description = "Private FQDN of the PostgreSQL Flexible Server."
  value       = azurerm_postgresql_flexible_server.main.fqdn
}

output "api_identity_client_id" {
  description = "Client ID of the API managed identity."
  value       = azurerm_user_assigned_identity.api.client_id
}

output "worker_identity_client_id" {
  description = "Client ID of the worker managed identity."
  value       = azurerm_user_assigned_identity.worker.client_id
}

output "static_web_app_default_host_name" {
  description = "Public hostname of the Static Web App serving the SPA (the user-facing site origin)."
  value       = azurerm_static_web_app.frontend.default_host_name
}

output "static_web_app_api_key" {
  description = "Deployment token for the Static Web App, consumed by the frontend SWA deploy job (Azure/static-web-apps-deploy)."
  value       = azurerm_static_web_app.frontend.api_key
  sensitive   = true
}

output "api_identity_principal_id" {
  description = "Object (principal) ID of the API MI — target for the out-of-band Graph Mail.Send grant (docs/ops/RUNBOOK.md)."
  value       = azurerm_user_assigned_identity.api.principal_id
}

output "worker_identity_principal_id" {
  description = "Object (principal) ID of the worker MI — target for the out-of-band Graph Mail.Send grant (docs/ops/RUNBOOK.md)."
  value       = azurerm_user_assigned_identity.worker.principal_id
}
