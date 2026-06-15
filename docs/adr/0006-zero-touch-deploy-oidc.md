# ADR-0006: Zero-Touch Production Deploy via GitHub Actions OIDC

## Status

Accepted (2026-06-15; implemented in Task 29)

## Context

Task 29 wires the production deploy pipeline. CONTEXT.md §Supply chain & CI/CD
requires: GitHub Actions → Azure via **OIDC only** (no long-lived Azure
credentials in GitHub), prod deploy on **`main` only**, immutable **SHA-tagged**
images (never `:latest`), and deploys that run only after PR checks pass.

The product owner asked for **zero-touch deployment**. Clarifying what that means
in practice surfaced two constraints that the naive "automate everything in one
pipeline" reading violates:

1. **The Exchange Application Access Policy** (RUNBOOK §2b) that constrains
   `Mail.Send` to the `noreply@dnblabs.co.uk` mailbox has **no Graph/ARM/Terraform
   resource** and **no OIDC path** — `Connect-ExchangeOnline` app-only auth
   mandates a long-lived **certificate**. Automating it would put a long-lived
   credential in GitHub, directly violating the OIDC-only guardrail.

2. **The Graph `Mail.Send` grant** (RUNBOOK §2a) is automatable as Terraform
   (`azuread_app_role_assignment`), but only if the applying identity holds
   tenant-wide **`AppRoleAssignment.ReadWrite.All`** — the power to grant *any*
   app *any* Graph permission. Putting that on the high-frequency, per-merge
   deploy robot is a large, unnecessary blast radius.

Industry practice separates three tiers: **Day-0 IAM/trust bootstrap** (rare,
privileged, ideally IaC), **infra changes** (`terraform apply`), and the
**application release** (every merge, minimally privileged). "Zero-touch
deployment" names the third tier, not "the CI principal performs tenant
administration on every run."

## Decision

**Zero-touch the application release; keep one-time IAM as separately-applied IaC
or a documented admin step. The per-merge pipeline never holds tenant-admin keys.**

- **Per-merge deploy** (`.github/workflows/deploy.yml`): triggered by
  `workflow_run` on CI **success** on `main` (the "requires PR checks" gate),
  plus `workflow_dispatch` for manual runs / rollback. It authenticates via OIDC
  (`azure/login@v2`, Terraform `ARM_USE_OIDC`), builds one SHA-tagged backend
  image (API and worker share it), `terraform apply`s the app stack, syncs Key
  Vault secret values from GitHub secrets, pins both Container App revisions to
  the SHA (`az containerapp update --image`), and smoke-tests `/health`.

- **Deploy identity** (`infra/bootstrap/deploy_identity.tf`): an Entra app +
  service principal with a **federated credential** trusting only
  `repo:DNBLabs/ai-job-matcher-and-cv-analyzer:ref:refs/heads/main`. Roles:
  Contributor + User Access Administrator (the app stack creates role
  assignments) + AcrPush + Storage Blob Data Owner on the state account.
  **Not granted:** `AppRoleAssignment.ReadWrite.All`.

- **`Mail.Send` grant** (`infra/grants/`): a separate, operator-applied Terraform
  stack (own state, run once with `az login` after the app stack). Keeps the
  privileged Graph grant off the routine pipeline.

- **Exchange Application Access Policy**: remains the single documented one-time
  admin step (RUNBOOK §2b). This is the correct outcome, not a gap — there is no
  OIDC-compatible path, and the OIDC-only guardrail takes precedence.

### Key Vault network ACL vs. GitHub-hosted runners

The Key Vault denies by default (`network_acls.default_action = "Deny"`). A
GitHub-hosted runner has an unpredictable egress IP, so `terraform apply` (which
creates KV secret resources — a data-plane write) and the secret-sync step would
be denied. The workflow passes the runner's current IP via `operator_ip_rules`
to the apply (so the ACL is created/updated to allow it) and removes it again in
an `always()` cleanup step, minimizing the exposure window.

## Consequences

**Positive**

- OIDC-only honored end to end; no long-lived Azure credential in GitHub.
- The high-frequency path is least-privileged: it cannot grant Graph permissions
  or modify Exchange.
- Immutable SHA tags + single-revision pinning give a deterministic rollback.

**Negative / accepted**

- Two one-time operator actions remain (the `infra/grants/` apply and the
  Exchange policy). Documented in RUNBOOK; correct by separation-of-duties.
- The per-merge pipeline still holds Contributor + User Access Administrator
  because it runs `terraform apply` of a stack that manages RBAC. A future
  hardening could split a gated "infra apply" workflow from a low-privilege
  "image deploy" workflow.
- Third-party API keys originate as a one-time human seed into GitHub secrets
  (unavoidable: they are not Azure-generated), then sync into Key Vault.
- The KV ACL briefly trusts the runner IP during a deploy.

## Rollback

Images are immutable and SHA-tagged, so a prior good build is always present in
ACR. To roll back:

1. Run the **Deploy (prod)** workflow via `workflow_dispatch` with `image_sha`
   set to the previous good commit SHA. The workflow skips the build and pins
   both Container Apps to that existing image.
2. Equivalent manual path: `az containerapp update -n <app> -g <rg> --image
   <acr>/backend:<prev-sha>` for the API and worker apps.
3. For an infra regression, `git revert` the offending merge and let the deploy
   pipeline re-apply (revert first, debug second).

## References

- CONTEXT.md §Supply chain & CI/CD; §Network (Key Vault ACL).
- ADR-0005 (Graph sendMail / Managed Identity email); RUNBOOK §2.
- memory: task29-zero-touch-deploy (feasibility analysis, 2026-06-15).
- GitHub–Azure OIDC: https://github.com/Azure/login
- azuread federated credential / app role assignment (provider docs, PIN ~> 3.0).
