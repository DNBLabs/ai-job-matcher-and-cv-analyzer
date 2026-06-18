# Operations Runbook

Out-of-band setup and incident-response steps. Most of the post-`terraform apply`
toil is now automated by the deploy pipeline (Task 29 / ADR-0006); what remains
below is genuinely one-time (IAM/trust bootstrap) or has no OIDC-compatible path.

## 0. One-time deploy bootstrap (per environment)

The deploy identity and GitHub secrets are set up once, by the operator.

1. **Apply the bootstrap stack** (`infra/bootstrap`) with `az login`. Besides the
   remote-state storage, it now creates the GitHub Actions **OIDC deploy
   identity**: an Entra app + service principal + a federated credential trusting
   only this repo on `main`, with Contributor + User Access Administrator +
   AcrPush + Storage Blob Data Owner. No client secret exists.

2. **Set GitHub Actions repository secrets** (Settings → Secrets and variables →
   Actions). From the bootstrap outputs:

   | GitHub secret | Source |
   |---|---|
   | `AZURE_CLIENT_ID` | `terraform output -raw deploy_client_id` |
   | `AZURE_TENANT_ID` | `terraform output -raw tenant_id` |
   | `AZURE_SUBSCRIPTION_ID` | `terraform output -raw subscription_id` |
   | `TFSTATE_STORAGE_ACCOUNT` | `terraform output -raw storage_account_name` |
   | `OWNER_EMAIL` | operator email (feeds the `owner` tag) |
   | `GOOGLE_OAUTH_CLIENT_SECRET` | Google Cloud console (one-time seed) |
   | `OPENAI_API_KEY` | OpenAI dashboard (one-time seed) |
   | `ADZUNA_APP_ID` / `ADZUNA_APP_KEY` | Adzuna developer portal (one-time seed) |

   The five secret *values* (OAuth/OpenAI/Adzuna) originate from third parties —
   seeding them into GitHub once is unavoidable. The pipeline syncs them into Key
   Vault on every deploy (skipping any that are unset).

3. **Apply the Mail.Send grant** (`infra/grants`) once with `az login`, after the
   app stack exists — see §2a.

4. **Apply the Exchange Application Access Policy** once — see §2b.

After this, merges to `main` deploy with no manual steps.

## 1. Key Vault secret values (now automated)

Terraform creates placeholder secrets so per-secret RBAC scopes exist
(`infra/app/keyvault.tf`); the **deploy pipeline** sets the real values from the
GitHub secrets in §0 (`az keyvault secret set`), so they never enter Terraform
state or git. Manual fallback if deploying outside the pipeline:

```bash
KV=$(terraform -chdir=infra/app output -raw key_vault_name)
az keyvault secret set --vault-name "$KV" --name google-oauth-client-secret --value "<...>"
az keyvault secret set --vault-name "$KV" --name openai-api-key            --value "<...>"
az keyvault secret set --vault-name "$KV" --name adzuna-app-id             --value "<...>"
az keyvault secret set --vault-name "$KV" --name adzuna-app-key            --value "<...>"
az keyvault secret set --vault-name "$KV" --name reed-api-key              --value "<...>"
```

The `database-password` secret is generated and owned by Terraform — do not set it.

## 2. Grant + constrain Microsoft Graph `Mail.Send` (transactional email)

Email is sent from `noreply@dnblabs.co.uk` via Graph `sendMail`, authenticated
by the API and Worker Managed Identities (ADR-0005). The grant is now IaC; the
Exchange constraint remains a manual admin step (no OIDC path — ADR-0006).

### 2a. Grant the `Mail.Send` application role to both MIs (IaC, one-time)

Applied once by the operator, off the routine deploy pipeline so the pipeline
never needs tenant-wide `AppRoleAssignment.ReadWrite.All` (ADR-0006):

```bash
export ARM_SUBSCRIPTION_ID="$(az account show --query id -o tsv)"
cd infra/grants
terraform init
terraform apply   # az login identity must hold Application Administrator
```

This creates the `azuread_app_role_assignment` (Mail.Send) for both managed
identities. Re-running is idempotent.

### 2b. Constrain the grant to ONLY the shared mailbox (mandatory)

Unconstrained `Mail.Send` lets the MI send as **any** tenant mailbox. Scope it to
`noreply@dnblabs.co.uk` with an Exchange Online Application Access Policy
(Exchange Online PowerShell — `Connect-ExchangeOnline` first):

```powershell
# Run once per MI app (use each MI's Application/client id, not the object id).
New-ApplicationAccessPolicy `
  -AppId <api-mi-client-id>,<worker-mi-client-id> `
  -PolicyScopeGroupId noreply@dnblabs.co.uk `
  -AccessRight RestrictAccess `
  -Description "AI Job Matcher: restrict Mail.Send to the noreply shared mailbox"

# Verify the policy denies all other mailboxes and allows the shared one:
Test-ApplicationAccessPolicy -Identity noreply@dnblabs.co.uk -AppId <api-mi-client-id>
Test-ApplicationAccessPolicy -Identity someone-else@dnblabs.co.uk -AppId <api-mi-client-id>  # expect Denied
```

### 2c. Post-deploy verification

- Trigger a magic-link sign-in and confirm the email lands in a real inbox from
  `noreply@dnblabs.co.uk`.
- Confirm app-only `sendMail` to the shared mailbox does not require a per-mailbox
  licence.

## 2d. Database migrations (after the first deploy / on schema changes)

Prod Postgres is VNet-private, so migrations run **inside** a container (which is
on the VNet). The backend image ships `alembic.ini` + `alembic/`:

```bash
az containerapp exec -n ca-ai-job-matcher-api -g rg-ai-job-matcher-prod \
  --command "alembic upgrade head"
```

Run once after the first successful deploy, and after any migration is added.

## 3. Incident response

See `docs/security/THREAT_MODEL.md` §8 for OpenAI key compromise, session
hijack, malicious image, and admin-account compromise procedures.
