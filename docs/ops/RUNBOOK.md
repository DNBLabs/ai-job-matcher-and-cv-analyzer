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

## 3. Observability

### 3a. Log Analytics workspace

ACA stdout is ingested automatically into the Log Analytics workspace
(`log-ai-job-matcher-prod`) via `log_analytics_workspace_id` on the container
app environment (`infra/app/containerapps.tf:47`, `infra/app/observability.tf`).
Logs land in `ContainerAppConsoleLogs_CL`; system events in
`ContainerAppSystemLogs_CL`.

**Cost**: PerGB2018 SKU, 30-day retention. At demo traffic (< 1 GB/month) the
bill is negligible (< £2/month).

**Azure Cost Management link** — view the resource group spend:

```
https://portal.azure.com/#blade/Microsoft_Azure_CostManagement/Menu/costanalysis
```

Navigate to **Subscription → Resource group → rg-ai-job-matcher-prod** to
filter by resource group.

### 3b. Structured log events (app code)

The API and worker emit JSON-formatted event lines for key metrics. Query them
in Log Analytics with KQL:

```kql
// 5xx errors in the last hour
ContainerAppConsoleLogs_CL
| where TimeGenerated > ago(1h)
| where Log_s contains '"event": "http_5xx"'
| project TimeGenerated, Log_s

// 429 rate-limit hits
ContainerAppConsoleLogs_CL
| where TimeGenerated > ago(1h)
| where Log_s contains '"event": "http_429"'
| project TimeGenerated, Log_s

// Scrape failures
ContainerAppConsoleLogs_CL
| where TimeGenerated > ago(1h)
| where Log_s contains '"event": "scrape_failure"'
| project TimeGenerated, Log_s

// Queue processing latency (worker)
ContainerAppConsoleLogs_CL
| where TimeGenerated > ago(1h)
| where Log_s contains '"event": "queue_message_processed"'
| project TimeGenerated, Log_s
```

No PII appears in these events — no user IDs, CV text, job titles, or email
addresses.

## 4. Alerts

All alerts notify `var.owner_email` via the `ag-owner-ai-job-matcher-prod`
action group (`infra/app/monitoring.tf`).

### 4a. Budget alerts

Two monthly budgets on `rg-ai-job-matcher-prod`:

| Resource | Amount | Threshold | Type |
|---|---|---|---|
| `budget-ai-job-matcher-prod-warning` | £60 | 100% actual | Email on trigger |
| `budget-ai-job-matcher-prod-critical` | £75 | 100% actual | Email on trigger |

**Verify post-deploy:**

```bash
RG=$(terraform -chdir=infra/app output -raw resource_group_name)
az consumption budget list --resource-group "$RG" --query "[].{name:name,amount:amount}"
```

**Response on trigger:**

1. Open Azure Cost Management and identify the high-spend service (likely
   OpenAI scoring or PostgreSQL compute).
2. If within the £60–£75 band: review Analysis Run frequency and scoring costs;
   consider raising the per-run listing cap or reducing scoring model calls.
3. If the £75 budget fires: scale down Container App replicas and suspend
   non-critical analysis runs until spend is confirmed under control.

### 4b. Service Bus queue-depth alert

Alert rule: `alert-sb-queue-depth-ai-job-matcher-prod`

Fires when `ActiveMessages` on the `analysis-runs` queue exceeds **10 for 15
minutes** (evaluated every 5 minutes). Severity 2 (Warning).

**Verify post-deploy:**

```bash
RG=$(terraform -chdir=infra/app output -raw resource_group_name)
az monitor metrics alert list --resource-group "$RG" \
  --query "[?contains(name,'sb-queue-depth')].{name:name,enabled:enabled}"
```

**Response on trigger:**

1. Check whether the worker Container App is running (`az containerapp show`).
2. Inspect worker logs for poison-message loops or scoring timeouts.
3. If the queue is genuinely backed up, scale the worker min replicas to 1
   temporarily:
   ```bash
   az containerapp update -n ca-ai-job-matcher-worker -g "$RG" \
     --min-replicas 1
   ```
4. Once the queue clears, revert to 0 min replicas.

## 5. OpenAI FinOps

### 5a. Daily spend alert (manual — OpenAI dashboard)

OpenAI does not expose a Cost Management–compatible API, so the £2/day alert
cannot be provisioned by Terraform. Set it up once:

1. Log in to [platform.openai.com](https://platform.openai.com).
2. Go to **Settings → Billing → Usage limits**.
3. Set **Soft limit** to **£2/day** (email notification only).
4. Set **Hard limit** to **£5/day** (API requests blocked above this).

These limits apply at the organisation level and cover all API calls, including
GPT-4o scoring and GPT-4o-mini title suggestions.

### 5b. Per-run cost tracking

FinOps data is logged to `finops_json` on each `analysis_run` row. Query prod
Postgres via `az containerapp exec`:

```bash
az containerapp exec -n ca-ai-job-matcher-api -g rg-ai-job-matcher-prod \
  --command "psql \$DATABASE_URL -c \
  \"SELECT id, finops_json->>'estimated_usd' AS usd FROM analysis_run ORDER BY created_at DESC LIMIT 10;\""
```

## 6. Incident response

See `docs/security/THREAT_MODEL.md` §8 for OpenAI key compromise, session
hijack, malicious image, and admin-account compromise procedures.

## 7. Custom domains (Cloudflare DNS + ACA managed cert)

Implements ADR-0011: `www.getmeajob.dnblabs.co.uk` (SWA) and
`api.getmeajob.dnblabs.co.uk` (ACA). Both are provisioned in a single
`terraform apply`; no manual DNS edits are needed after bootstrap.

### 7a. Before first deploy with this change (one-time operator steps)

1. **Create a Cloudflare API token** in the Cloudflare dashboard
   (My Profile → API Tokens → Create Token):
   - Template: *Edit zone DNS*
   - Permissions: `Zone / DNS / Edit` and `Zone / Zone / Read`
   - Zone resources: Include → Specific zone → `dnblabs.co.uk`
   - Do **not** add broader permissions; the token is scoped to DNS edits only.

2. **Add GitHub Actions secrets** (Settings → Secrets and variables → Actions):

   | GitHub secret | Value |
   |---|---|
   | `CLOUDFLARE_API_TOKEN` | Token created in step 1 |
   | `CLOUDFLARE_ZONE_ID` | Zone ID from Cloudflare dashboard (Overview → right panel → Zone ID) for `dnblabs.co.uk` |

   Until both secrets are set, the `Terraform apply` step will fail with an
   authentication error from the Cloudflare provider.

### 7b. Deployment sequencing

1. **Single `terraform apply`** creates all four resources:
   - `cloudflare_dns_record.frontend_cname` — `www` CNAME → SWA hostname
   - `cloudflare_dns_record.api_cname` — `api` CNAME → ACA native FQDN
   - `azurerm_static_web_app_custom_domain.frontend` — registers and validates with Azure
   - `azurerm_container_app_custom_domain.api` — registers with Azure; cert provisioned async

2. **SWA cert** (for `www.getmeajob.dnblabs.co.uk`) provisions within minutes;
   the site should be reachable over HTTPS shortly after apply.

3. **ACA managed cert** (for `api.getmeajob.dnblabs.co.uk`) is asynchronous.
   Confirm it is `Approved` before merging the follow-on issue that promotes
   `api_public_url` to the custom domain:

   ```bash
   az containerapp show \
     -n ca-ai-job-matcher-api \
     -g rg-ai-job-matcher-prod \
     --query "properties.customDomains[?name=='api.getmeajob.dnblabs.co.uk'].bindingType" \
     -o tsv
   ```

   Expected value: `SniEnabled` (Azure sets this once the cert is `Approved`).
   If the cert is still provisioning, wait a few minutes and re-check.

   > **Important:** Do NOT merge the issue that changes `api_public_url` to
   > `api.getmeajob.dnblabs.co.uk` until the cert above is confirmed `Approved`.
   > Changing `api_public_url` before then will break `GOOGLE_OAUTH_REDIRECT_URI`.
