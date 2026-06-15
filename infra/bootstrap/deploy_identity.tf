# GitHub Actions OIDC deploy identity (Task 29).
#
# A single Entra application + service principal that the deploy workflow assumes
# via OIDC federation — NO client secret, NO long-lived Azure credential in
# GitHub (CONTEXT.md §Supply chain & CI/CD). The federated credential trusts only
# this repository on the `main` branch, so forks and feature branches cannot
# assume it.
#
# Least privilege (the high-frequency, per-merge path holds only what shipping
# the app requires):
#   - Contributor + User Access Administrator (subscription): apply the app stack,
#     which itself creates azurerm role assignments (needs roleAssignments/write).
#   - AcrPush (subscription): push SHA-tagged images. Data-plane role; the registry
#     is created by the app stack so the scope is the subscription, not the ACR.
#   - Storage Blob Data Owner (state account): read/write the azurerm remote state
#     (use_azuread_auth = true; no shared keys).
#
# Deliberately NOT granted: tenant-wide Microsoft Graph AppRoleAssignment.ReadWrite.All.
# The Mail.Send grant is a one-time operator action in infra/grants/ (ADR-0006),
# keeping the routine deploy robot unable to grant arbitrary Graph permissions.

data "azurerm_subscription" "current" {}

resource "azuread_application_registration" "deploy" {
  display_name = "gh-deploy-${var.project}"
  description  = "GitHub Actions OIDC deploy identity for ${var.github_repository} (Task 29)."
}

resource "azuread_service_principal" "deploy" {
  client_id = azuread_application_registration.deploy.client_id
}

# Federated credential: trusts GitHub's OIDC issuer for this repo on `main` only.
# Subject/issuer/audience per the GitHub-Azure OIDC contract.
# Source: https://github.com/hashicorp/terraform-provider-azuread/blob/main/docs/resources/application_federated_identity_credential.md
resource "azuread_application_federated_identity_credential" "deploy_main" {
  application_id = azuread_application_registration.deploy.id
  display_name   = "github-${var.github_deploy_branch}"
  description    = "GitHub Actions OIDC from ${var.github_repository}@${var.github_deploy_branch}"
  audiences      = ["api://AzureADTokenExchange"]
  issuer         = "https://token.actions.githubusercontent.com"
  subject        = "repo:${var.github_repository}:ref:refs/heads/${var.github_deploy_branch}"
}

# ---- Subscription-scoped role assignments -----------------------------------

resource "azurerm_role_assignment" "deploy_contributor" {
  scope                = data.azurerm_subscription.current.id
  role_definition_name = "Contributor"
  principal_id         = azuread_service_principal.deploy.object_id
}

# Required because the app stack creates azurerm_role_assignment resources
# (AcrPull / Blob / Service Bus / Key Vault) — Contributor cannot write role
# assignments; User Access Administrator can.
resource "azurerm_role_assignment" "deploy_uaa" {
  scope                = data.azurerm_subscription.current.id
  role_definition_name = "User Access Administrator"
  principal_id         = azuread_service_principal.deploy.object_id
}

# Data-plane push for `az acr login` + docker push (admin user is disabled).
resource "azurerm_role_assignment" "deploy_acrpush" {
  scope                = data.azurerm_subscription.current.id
  role_definition_name = "AcrPush"
  principal_id         = azuread_service_principal.deploy.object_id
}

# Remote Terraform state lives in this account; the backend uses Azure AD auth.
resource "azurerm_role_assignment" "deploy_state_blob" {
  scope                = azurerm_storage_account.tfstate.id
  role_definition_name = "Storage Blob Data Owner"
  principal_id         = azuread_service_principal.deploy.object_id
}
