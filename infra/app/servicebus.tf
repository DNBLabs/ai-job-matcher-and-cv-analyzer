# Service Bus queue for Analysis Runs. Basic SKU (docs/finance/BUDGET.md: £8).
#
# DEVIATION (recorded in docs/adr/0004-service-bus-basic-no-private-endpoint.md):
# CONTEXT.md §Network lists a private endpoint for Service Bus, but Private Link
# requires the Premium SKU (~£500+/mo), which breaks the £75 hard cap. Basic has
# a public endpoint with no network isolation. Compensating controls:
#   - Application data-plane (send/receive) authenticates via managed identity +
#     Azure RBAC (Data Sender / Data Receiver) — see identity.tf.
#   - The only SAS key is a single Listen-only, queue-scoped rule consumed solely
#     by the worker's KEDA scaler (ACA's azurerm custom_scale_rule supports only
#     connection-string auth, not managed identity).
resource "azurerm_servicebus_namespace" "main" {
  name                = local.servicebus_name
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  sku                 = "Basic"

  # Keep SAS enabled because the KEDA scaler needs a connection string; app code
  # still uses managed identity for send/receive. (local_auth cannot be disabled
  # while the KEDA Listen rule is in use.)
  local_auth_enabled = true

  tags = local.common_tags
}

resource "azurerm_servicebus_queue" "analysis_runs" {
  name         = local.servicebus_queue_name
  namespace_id = azurerm_servicebus_namespace.main.id

  # Workers retry each Job Source up to 2 times (CONTEXT.md §Run Failure).
  max_delivery_count = 3
}

# Listen-only SAS rule, queue-scoped — least privilege for the KEDA scaler only.
resource "azurerm_servicebus_queue_authorization_rule" "keda_listen" {
  name     = "keda-listen"
  queue_id = azurerm_servicebus_queue.analysis_runs.id

  listen = true
  send   = false
  manage = false
}
