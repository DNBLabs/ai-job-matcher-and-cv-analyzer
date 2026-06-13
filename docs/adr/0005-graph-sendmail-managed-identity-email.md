# ADR-0005: Transactional Email via Microsoft Graph sendMail with Managed Identity

## Status

Accepted (2026-06-11; implemented in Task 27)

Supersedes the Resend adapter shipped in Task 19.

## Context

The MVP sends two transactional emails: the magic-link sign-in email (from the
API) and the run-completion email (from the worker). Task 19 shipped a `Resend`
adapter behind the `NotificationPort`, with the API key resolved from Key Vault.

Two problems with Resend for this deployment:

- It introduces a **stored API key** (one more secret to rotate and protect),
  contrary to the "no stored key" posture the rest of the Azure stack achieves
  with Managed Identity.
- Deliverability would depend on warming a **new sender domain**.

The operator already owns the `dnblabs.co.uk` Microsoft 365 tenant, where
SPF/DKIM/DMARC are established, and a shared mailbox `noreply@dnblabs.co.uk`.

## Decision

Send transactional email from the **M365 shared mailbox `noreply@dnblabs.co.uk`**
via the **Microsoft Graph `sendMail` API**, authenticated by the Container App
**Managed Identity** — no API key is stored.

- Endpoint: `POST https://graph.microsoft.com/v1.0/users/noreply@dnblabs.co.uk/sendMail`
  (token scope `https://graph.microsoft.com/.default`, success `202 Accepted`).
- Adapter: `GraphApiNotificationPort` behind the existing `NotificationPort`.
  The Resend adapter is removed.
- Both the **API MI** and the **Worker MI** are granted the Graph **`Mail.Send`
  application** permission (API sends magic links; worker sends run-complete).

### Least privilege (mandatory)

`Mail.Send` *application* permission grants send-as **any** tenant mailbox by
default. It **must** be constrained to only `noreply@dnblabs.co.uk` with an
Exchange Online **Application Access Policy** (`New-ApplicationAccessPolicy`).
There is no Terraform/`azurerm` resource for this; it is an out-of-band operator
step, exactly like setting real Key Vault secret values. See
[docs/ops/RUNBOOK.md](../ops/RUNBOOK.md).

## Consequences

### Positive

- No stored email secret; the email path inherits the MI posture of the rest of
  the stack (THREAT_MODEL §"OAuth client secret / email" asset — the email API
  key is eliminated entirely).
- Deliverability rides the established `dnblabs.co.uk` domain reputation.
- `EMAIL_FROM` / `NOTIFICATION_BACKEND=graph` are plain env on both Container
  Apps (`infra/app/containerapps.tf`); local dev keeps the `log` adapter.

### Negative

- The `Mail.Send` grant and the Application Access Policy are **manual**
  out-of-band steps the operator must perform once per environment, and verify.
  Forgetting the Access Policy leaves the MI able to send as any mailbox.
- Graph throttling / Exchange Online send limits apply (acceptable at Profile A
  volume).
- `azurerm` cannot express the Microsoft Graph app-role assignment or the
  Exchange policy, so they live in a runbook rather than IaC.

### Follow-ups

- Post-deploy: real-inbox deliverability check from the shared mailbox
  (Task 27 verification; deferred until a deploy target exists).
- Confirm app-only `sendMail` to the shared mailbox needs no per-mailbox licence.
- `API_BASE_URL` / `FRONTEND_BASE_URL` (used to build the links inside the
  emails) are set at deploy time once the public hostname is fixed (Task 29).
