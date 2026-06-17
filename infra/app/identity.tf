# Two user-assigned managed identities with split, least-privilege access
# (CONTEXT.md §Runtime & IAM; THREAT_MODEL.md R3/R4):
#
#   API MI    : Blob RW on cvs/; Service Bus send; Key Vault get OAuth+OpenAI+DB; ACR pull
#   Worker MI : Blob read-only on cvs/; Service Bus receive; Key Vault get OpenAI+Adzuna+DB; ACR pull
#
# Key Vault access is scoped per-secret (not vault-wide). OpenAI is shared: the
# API runs the sync title-suggestion call in-process and the Worker runs scoring,
# so both need openai-api-key. Adzuna stays Worker-only (job search runs there).

resource "azurerm_user_assigned_identity" "api" {
  name                = "id-${var.project}-api"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  tags                = local.common_tags
}

resource "azurerm_user_assigned_identity" "worker" {
  name                = "id-${var.project}-worker"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  tags                = local.common_tags
}

# ---- ACR pull (both apps) ----------------------------------------------------

resource "azurerm_role_assignment" "api_acr_pull" {
  scope                = azurerm_container_registry.main.id
  role_definition_name = "AcrPull"
  principal_id         = azurerm_user_assigned_identity.api.principal_id
}

resource "azurerm_role_assignment" "worker_acr_pull" {
  scope                = azurerm_container_registry.main.id
  role_definition_name = "AcrPull"
  principal_id         = azurerm_user_assigned_identity.worker.principal_id
}

# ---- Blob: API read/write/delete, Worker read-only (scoped to cvs container) -

resource "azurerm_role_assignment" "api_blob_contributor" {
  scope                = azurerm_storage_container.cvs.id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = azurerm_user_assigned_identity.api.principal_id
}

resource "azurerm_role_assignment" "worker_blob_reader" {
  scope                = azurerm_storage_container.cvs.id
  role_definition_name = "Storage Blob Data Reader"
  principal_id         = azurerm_user_assigned_identity.worker.principal_id
}

# ---- Service Bus: API sends, Worker receives (scoped to the queue) -----------

resource "azurerm_role_assignment" "api_sb_sender" {
  scope                = azurerm_servicebus_queue.analysis_runs.id
  role_definition_name = "Azure Service Bus Data Sender"
  principal_id         = azurerm_user_assigned_identity.api.principal_id
}

resource "azurerm_role_assignment" "worker_sb_receiver" {
  scope                = azurerm_servicebus_queue.analysis_runs.id
  role_definition_name = "Azure Service Bus Data Receiver"
  principal_id         = azurerm_user_assigned_identity.worker.principal_id
}

# ---- Key Vault: per-secret Secrets User --------------------------------------

# API reads the Google OAuth client id + secret + the shared DB password.
resource "azurerm_role_assignment" "api_kv_oauth" {
  scope                = azurerm_key_vault_secret.placeholders["google-oauth-client-secret"].resource_versionless_id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = azurerm_user_assigned_identity.api.principal_id
}

resource "azurerm_role_assignment" "api_kv_oauth_client_id" {
  scope                = azurerm_key_vault_secret.placeholders["google-oauth-client-id"].resource_versionless_id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = azurerm_user_assigned_identity.api.principal_id
}

resource "azurerm_role_assignment" "api_kv_db" {
  scope                = azurerm_key_vault_secret.database_password.resource_versionless_id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = azurerm_user_assigned_identity.api.principal_id
}

# API also reads openai-api-key: the sync Suggested Job Titles call runs in the
# API process (POST /cvs/{id}/suggest-titles -> create_llm_client). Without this
# the API MI gets ForbiddenByRbac on getSecret and every title suggestion fails
# (issue #52). Shared with the Worker, which uses the same key for scoring.
resource "azurerm_role_assignment" "api_kv_openai" {
  scope                = azurerm_key_vault_secret.placeholders["openai-api-key"].resource_versionless_id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = azurerm_user_assigned_identity.api.principal_id
}

# Worker reads only OpenAI + Adzuna secrets + the shared DB password.
resource "azurerm_role_assignment" "worker_kv_openai_adzuna" {
  for_each = toset(["openai-api-key", "adzuna-app-id", "adzuna-app-key"])

  scope                = azurerm_key_vault_secret.placeholders[each.key].resource_versionless_id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = azurerm_user_assigned_identity.worker.principal_id
}

resource "azurerm_role_assignment" "worker_kv_db" {
  scope                = azurerm_key_vault_secret.database_password.resource_versionless_id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = azurerm_user_assigned_identity.worker.principal_id
}
