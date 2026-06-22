# FinOps and observability alerts.
#
# 1. Email action group — single notification target for all alert rules below.
# 2. Two monthly budget alerts on the resource group (£60 warning / £75 critical).
# 3. Service Bus queue-depth alert — ActiveMessages > 10 for 15 min.

resource "azurerm_monitor_action_group" "owner_email" {
  name                = "ag-owner-${local.name_prefix}"
  resource_group_name = azurerm_resource_group.main.name
  short_name          = "owner-email"

  email_receiver {
    name          = "owner"
    email_address = var.owner_email
  }

  tags = local.common_tags
}

# £60 warning budget — fires when actual spend reaches 100% of this amount.
resource "azurerm_consumption_budget_resource_group" "warning" {
  name              = "budget-${local.name_prefix}-warning"
  resource_group_id = azurerm_resource_group.main.id
  amount            = 60
  time_grain        = "Monthly"

  time_period {
    # Azure enforces: start_date >= first day of the current billing month.
    # Update this if the budget is destroyed and re-created in a later month.
    start_date = "2026-06-01T00:00:00Z"
  }

  notification {
    enabled        = true
    threshold      = 100
    operator       = "GreaterThanOrEqualTo"
    threshold_type = "Actual"

    contact_groups = [azurerm_monitor_action_group.owner_email.id]
  }
}

# £75 critical budget — hard cap per docs/finance/BUDGET.md.
resource "azurerm_consumption_budget_resource_group" "critical" {
  name              = "budget-${local.name_prefix}-critical"
  resource_group_id = azurerm_resource_group.main.id
  amount            = 75
  time_grain        = "Monthly"

  time_period {
    # Azure enforces: start_date >= first day of the current billing month.
    # Update this if the budget is destroyed and re-created in a later month.
    start_date = "2026-06-01T00:00:00Z"
  }

  notification {
    enabled        = true
    threshold      = 100
    operator       = "GreaterThanOrEqualTo"
    threshold_type = "Actual"

    contact_groups = [azurerm_monitor_action_group.owner_email.id]
  }
}

# Service Bus queue-depth alert. Basic SKU exposes ActiveMessages at the
# namespace level; EntityName dimension scopes it to the analysis-runs queue.
# Fires when the maximum active message count exceeds 10 across a 15-min window,
# evaluated every 5 minutes. Severity 2 (Warning).
resource "azurerm_monitor_metric_alert" "servicebus_queue_depth" {
  name                = "alert-sb-queue-depth-${local.name_prefix}"
  resource_group_name = azurerm_resource_group.main.name
  scopes              = [azurerm_servicebus_namespace.main.id]
  description         = "Service Bus ${local.servicebus_queue_name}: ActiveMessages > 10 for 15 min"
  severity            = 2
  frequency           = "PT5M"
  window_size         = "PT15M"
  enabled             = true

  criteria {
    metric_namespace = "Microsoft.ServiceBus/namespaces"
    metric_name      = "ActiveMessages"
    aggregation      = "Maximum"
    operator         = "GreaterThan"
    threshold        = 10

    dimension {
      name     = "EntityName"
      operator = "Include"
      values   = [local.servicebus_queue_name]
    }
  }

  action {
    action_group_id = azurerm_monitor_action_group.owner_email.id
  }

  tags = local.common_tags
}
