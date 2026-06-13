# Container Apps Environment + the API and worker apps.
#
# The environment is VNet-integrated (infrastructure_subnet_id) so the apps
# reach Postgres/Blob/Key Vault over the private network. internal_load_balancer
# stays false: the API needs public HTTPS ingress; the worker has no ingress.

variable "allowed_origins" {
  description = "Comma-separated CORS origins for the API (frontend URL). Set after the frontend host is known."
  type        = string
  default     = ""
}

# Initial placeholder image; the deploy workflow (Task 29) pins SHA-tagged
# images from ACR. lifecycle ignore_changes hands image ownership to that
# pipeline so Terraform never reverts a deployed revision.
locals {
  placeholder_image    = "mcr.microsoft.com/k8se/quickstart:latest"
  servicebus_namespace = "${azurerm_servicebus_namespace.main.name}.servicebus.windows.net"
}

resource "azurerm_container_app_environment" "main" {
  name                       = "cae-${local.name_prefix}"
  resource_group_name        = azurerm_resource_group.main.name
  location                   = azurerm_resource_group.main.location
  log_analytics_workspace_id = azurerm_log_analytics_workspace.main.id

  infrastructure_subnet_id       = azurerm_subnet.aca.id
  internal_load_balancer_enabled = false # external env: API gets public ingress

  tags = local.common_tags
}

# ---- API app: public HTTPS ingress, min 0 / max 2 ---------------------------

resource "azurerm_container_app" "api" {
  name                         = "ca-${var.project}-api"
  resource_group_name          = azurerm_resource_group.main.name
  container_app_environment_id = azurerm_container_app_environment.main.id
  revision_mode                = "Single"
  tags                         = local.common_tags

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.api.id]
  }

  registry {
    server   = azurerm_container_registry.main.login_server
    identity = azurerm_user_assigned_identity.api.id
  }

  # Key Vault-backed secrets, resolved by the API managed identity.
  secret {
    name                = "database-password"
    key_vault_secret_id = azurerm_key_vault_secret.database_password.versionless_id
    identity            = azurerm_user_assigned_identity.api.id
  }
  secret {
    name                = "google-oauth-client-secret"
    key_vault_secret_id = azurerm_key_vault_secret.placeholders["google-oauth-client-secret"].versionless_id
    identity            = azurerm_user_assigned_identity.api.id
  }

  ingress {
    external_enabled = true
    target_port      = 8000
    transport        = "auto"

    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }

  template {
    min_replicas = 0
    max_replicas = 2

    container {
      name   = "api"
      image  = local.placeholder_image
      cpu    = 0.5
      memory = "1Gi"

      env {
        name  = "APP_ENV"
        value = "production"
      }
      env {
        name  = "ALLOWED_ORIGINS"
        value = var.allowed_origins
      }
      env {
        name  = "AZURE_CLIENT_ID"
        value = azurerm_user_assigned_identity.api.client_id
      }
      env {
        name  = "SECRET_PROVIDER_BACKEND"
        value = "keyvault"
      }
      env {
        name  = "KEY_VAULT_URI"
        value = azurerm_key_vault.main.vault_uri
      }
      env {
        name  = "BLOB_STORE_BACKEND"
        value = "azure"
      }
      env {
        name  = "BLOB_ACCOUNT_URL"
        value = azurerm_storage_account.main.primary_blob_endpoint
      }
      env {
        name  = "BLOB_CONTAINER_NAME"
        value = local.blob_container_name
      }
      env {
        name  = "BLOB_KEY_PREFIX"
        value = "cvs/"
      }
      env {
        name  = "JOB_QUEUE_BACKEND"
        value = "servicebus"
      }
      env {
        name  = "SERVICEBUS_NAMESPACE"
        value = local.servicebus_namespace
      }
      env {
        name  = "JOB_QUEUE_NAME"
        value = local.servicebus_queue_name
      }
      env {
        name  = "POSTGRES_HOST"
        value = azurerm_postgresql_flexible_server.main.fqdn
      }
      env {
        name  = "POSTGRES_DB"
        value = azurerm_postgresql_flexible_server_database.app.name
      }
      env {
        name  = "POSTGRES_USER"
        value = var.postgres_administrator_login
      }
      env {
        name        = "POSTGRES_PASSWORD"
        secret_name = "database-password"
      }
      env {
        name        = "GOOGLE_OAUTH_CLIENT_SECRET"
        secret_name = "google-oauth-client-secret"
      }
      # Transactional email via Microsoft Graph sendMail using the API MI
      # (CONTEXT 2026-06-11). No API key: Mail.Send is granted to the MI and
      # constrained to EMAIL_FROM by an Exchange Application Access Policy
      # (docs/adr/0005, docs/ops/RUNBOOK.md).
      env {
        name  = "NOTIFICATION_BACKEND"
        value = "graph"
      }
      env {
        name  = "EMAIL_FROM"
        value = var.email_from
      }
    }
  }

  lifecycle {
    ignore_changes = [template[0].container[0].image]
  }
}

# ---- Worker app: no ingress, KEDA Service Bus queue-depth scaling ------------

resource "azurerm_container_app" "worker" {
  name                         = "ca-${var.project}-worker"
  resource_group_name          = azurerm_resource_group.main.name
  container_app_environment_id = azurerm_container_app_environment.main.id
  revision_mode                = "Single"
  tags                         = local.common_tags

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.worker.id]
  }

  registry {
    server   = azurerm_container_registry.main.login_server
    identity = azurerm_user_assigned_identity.worker.id
  }

  secret {
    name                = "database-password"
    key_vault_secret_id = azurerm_key_vault_secret.database_password.versionless_id
    identity            = azurerm_user_assigned_identity.worker.id
  }
  secret {
    name                = "openai-api-key"
    key_vault_secret_id = azurerm_key_vault_secret.placeholders["openai-api-key"].versionless_id
    identity            = azurerm_user_assigned_identity.worker.id
  }
  secret {
    name                = "adzuna-app-id"
    key_vault_secret_id = azurerm_key_vault_secret.placeholders["adzuna-app-id"].versionless_id
    identity            = azurerm_user_assigned_identity.worker.id
  }
  secret {
    name                = "adzuna-app-key"
    key_vault_secret_id = azurerm_key_vault_secret.placeholders["adzuna-app-key"].versionless_id
    identity            = azurerm_user_assigned_identity.worker.id
  }

  # Connection string for the KEDA scaler ONLY (Listen-only, queue-scoped SAS).
  # ACA's custom_scale_rule supports connection-string auth only, not MI —
  # app data-plane receive still uses the worker MI. See servicebus.tf / ADR-0004.
  secret {
    name  = "servicebus-keda-connection"
    value = azurerm_servicebus_queue_authorization_rule.keda_listen.primary_connection_string
  }

  template {
    min_replicas = 0
    max_replicas = 2

    container {
      name    = "worker"
      image   = local.placeholder_image
      cpu     = 0.5
      memory  = "1Gi"
      command = ["python", "-m", "worker.main"]

      env {
        name  = "APP_ENV"
        value = "production"
      }
      env {
        name  = "AZURE_CLIENT_ID"
        value = azurerm_user_assigned_identity.worker.client_id
      }
      env {
        name  = "SECRET_PROVIDER_BACKEND"
        value = "keyvault"
      }
      env {
        name  = "KEY_VAULT_URI"
        value = azurerm_key_vault.main.vault_uri
      }
      env {
        name  = "BLOB_STORE_BACKEND"
        value = "azure"
      }
      env {
        name  = "BLOB_ACCOUNT_URL"
        value = azurerm_storage_account.main.primary_blob_endpoint
      }
      env {
        name  = "BLOB_CONTAINER_NAME"
        value = local.blob_container_name
      }
      env {
        name  = "JOB_QUEUE_BACKEND"
        value = "servicebus"
      }
      env {
        name  = "SERVICEBUS_NAMESPACE"
        value = local.servicebus_namespace
      }
      env {
        name  = "JOB_QUEUE_NAME"
        value = local.servicebus_queue_name
      }
      env {
        name  = "POSTGRES_HOST"
        value = azurerm_postgresql_flexible_server.main.fqdn
      }
      env {
        name  = "POSTGRES_DB"
        value = azurerm_postgresql_flexible_server_database.app.name
      }
      env {
        name  = "POSTGRES_USER"
        value = var.postgres_administrator_login
      }
      env {
        name        = "POSTGRES_PASSWORD"
        secret_name = "database-password"
      }
      env {
        name        = "OPENAI_API_KEY"
        secret_name = "openai-api-key"
      }
      env {
        name        = "ADZUNA_APP_ID"
        secret_name = "adzuna-app-id"
      }
      env {
        name        = "ADZUNA_APP_KEY"
        secret_name = "adzuna-app-key"
      }
      # Run-completion email via Microsoft Graph sendMail using the worker MI
      # (same shared mailbox + Application Access Policy as the API; docs/adr/0005).
      env {
        name  = "NOTIFICATION_BACKEND"
        value = "graph"
      }
      env {
        name  = "EMAIL_FROM"
        value = var.email_from
      }
    }

    # KEDA Service Bus queue-depth scaler (CONTEXT.md §Scaling; BUDGET.md).
    custom_scale_rule {
      name             = "servicebus-queue-depth"
      custom_rule_type = "azure-servicebus"

      metadata = {
        queueName    = local.servicebus_queue_name
        namespace    = azurerm_servicebus_namespace.main.name
        messageCount = "5"
      }

      authentication {
        secret_name       = "servicebus-keda-connection"
        trigger_parameter = "connection"
      }
    }
  }

  lifecycle {
    ignore_changes = [template[0].container[0].image]
  }
}
