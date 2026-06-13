# ADR-0004: Service Bus Basic with Managed-Identity Auth (no Private Endpoint)

## Status

Accepted (2026-06-13)

## Context

CONTEXT.md §Network and Task 26 list a **private endpoint** for Azure Service
Bus alongside Postgres and Blob, so that no application dependency is reachable
from the public internet. While provisioning the application Terraform stack
(`infra/app/`) this collided with two hard constraints:

1. **Private Link for Service Bus requires the Premium SKU.** Basic and Standard
   namespaces have no private-endpoint support. Premium is billed per messaging
   unit at **~£500+/month** — it single-handedly breaks the **£75/month hard
   cap** (docs/finance/BUDGET.md), which budgets Service Bus at the **Basic**
   tier (~£8/mo).
2. **Network isolation short of Private Link is also tier-gated.** IP firewall /
   VNet network rules need Standard or Premium; **Basic has a public endpoint
   with no network ACLs at all.**

So "Service Bus Basic" (BUDGET.md) and "Service Bus private endpoint"
(CONTEXT.md §Network) are mutually exclusive. The budget ceiling is a hard
constraint for a solo portfolio demo; the private endpoint is a defence-in-depth
control whose primary risk (data exfiltration / unauthorized queue access) can
be mitigated by other means.

A second, related constraint surfaced on the consumer side. The worker scales on
queue depth via **KEDA**, configured through the `azurerm_container_app`
`custom_scale_rule` block. That block supports **connection-string
(SAS) authentication only** — it exposes no managed-identity option. So the
KEDA scaler cannot use the worker's managed identity even though the application
data plane can.

## Decision

Provision Service Bus at the **Basic** SKU with a **public endpoint**, and
compensate for the absent private endpoint with identity-based access control:

1. **Application data plane uses Managed Identity + Azure RBAC.** The API
   identity holds **Azure Service Bus Data Sender** and the worker identity holds
   **Azure Service Bus Data Receiver**, both scoped to the single queue
   (`infra/app/identity.tf`). This matches THREAT_MODEL.md least privilege.
2. **Exactly one SAS key exists**, and only for the KEDA scaler: a **Listen-only,
   queue-scoped** authorization rule (`keda-listen`). It cannot send or manage.
   `local_auth_enabled` stays `true` solely because this rule is in use.
3. The scaler connection string is injected into the worker as a Container App
   secret used only by the scale rule; it is never used by application code.

Postgres (VNet-injected, private DNS) and Blob (private endpoint) keep their
private networking as specified — only Service Bus deviates.

## Consequences

### Positive

- Stays within the £75/month hard budget ceiling.
- No broad SAS keys: send/receive is identity-based and queue-scoped; the lone
  SAS key is Listen-only and queue-scoped — minimal blast radius if leaked.
- KEDA queue-depth scaling works with the supported `azurerm` configuration.

### Negative

- Service Bus has a **public endpoint**; an attacker with a valid token/key
  could reach it over the internet. Residual risk accepted for the demo;
  mitigated by RBAC scoping, the Listen-only SAS, queue-depth alerting
  (THREAT_MODEL.md), and the £2/day OpenAI spend alert bounding abuse cost.
- Divergence from CONTEXT.md §Network "private endpoint" for Service Bus — this
  ADR is the record of that exception.

### Revisit when

- The product leaves demo scale or the budget ceiling rises: move to **Service
  Bus Premium + private endpoint** and disable `local_auth_enabled` once KEDA
  managed-identity scaling is available in `azurerm_container_app`.
