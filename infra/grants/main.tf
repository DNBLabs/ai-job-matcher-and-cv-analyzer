# Grant Microsoft Graph Mail.Send to the API and worker managed identities so
# both can send transactional email via Graph sendMail (ADR-0005). This replaces
# RUNBOOK §2a's manual `az rest` calls with idempotent IaC.
#
# Mail.Send alone lets a managed identity send as ANY tenant mailbox; it MUST be
# constrained to noreply@dnblabs.co.uk by an Exchange Application Access Policy
# (RUNBOOK §2b). That policy has no Graph/Terraform/ARM resource and no OIDC
# path, so it stays a one-time admin step (ADR-0006).

locals {
  resource_group_name = "rg-${var.project}-${var.environment}"
}

# The MIs are created by the app stack; look them up by their deterministic names
# (infra/app/identity.tf: id-${project}-api / -worker). principal_id is each MI's
# service-principal object ID — the assignment target.
data "azurerm_user_assigned_identity" "api" {
  name                = "id-${var.project}-api"
  resource_group_name = local.resource_group_name
}

data "azurerm_user_assigned_identity" "worker" {
  name                = "id-${var.project}-worker"
  resource_group_name = local.resource_group_name
}

# Microsoft Graph first-party service principal; app_role_ids maps role names to
# their GUIDs in this tenant.
# Source: https://github.com/hashicorp/terraform-provider-azuread/blob/main/docs/resources/app_role_assignment.md
data "azuread_service_principal" "msgraph" {
  client_id = "00000003-0000-0000-c000-000000000000"
}

resource "azuread_app_role_assignment" "mail_send" {
  for_each = {
    api    = data.azurerm_user_assigned_identity.api.principal_id
    worker = data.azurerm_user_assigned_identity.worker.principal_id
  }

  app_role_id         = data.azuread_service_principal.msgraph.app_role_ids["Mail.Send"]
  principal_object_id = each.value
  resource_object_id  = data.azuread_service_principal.msgraph.object_id
}
