# Operations Runbook

Out-of-band setup and incident-response steps that are not expressed in
Terraform. Run once per environment after `terraform apply` of the application
stack (Task 26).

## 1. Set real Key Vault secret values

Terraform creates placeholder secrets so per-secret RBAC scopes exist
(`infra/app/keyvault.tf`); the real values are set out-of-band so they never
enter Terraform state or git:

```bash
KV=$(terraform -chdir=infra/app output -raw key_vault_name)
az keyvault secret set --vault-name "$KV" --name google-oauth-client-secret --value "<...>"
az keyvault secret set --vault-name "$KV" --name openai-api-key            --value "<...>"
az keyvault secret set --vault-name "$KV" --name adzuna-app-id             --value "<...>"
az keyvault secret set --vault-name "$KV" --name adzuna-app-key            --value "<...>"
```

The `database-password` secret is generated and owned by Terraform — do not set it.

## 2. Grant + constrain Microsoft Graph `Mail.Send` (transactional email)

Email is sent from `noreply@dnblabs.co.uk` via Graph `sendMail`, authenticated
by the API and Worker Managed Identities (ADR-0005). Two things must be done by
an Azure AD / Exchange administrator; neither has a Terraform resource.

### 2a. Grant the `Mail.Send` application role to both MIs

```bash
GRAPH_APP_ID=00000003-0000-0000-c000-000000000000   # Microsoft Graph
GRAPH_SP_ID=$(az ad sp show --id "$GRAPH_APP_ID" --query id -o tsv)
MAIL_SEND_ROLE_ID=$(az ad sp show --id "$GRAPH_APP_ID" \
  --query "appRoles[?value=='Mail.Send'].id | [0]" -o tsv)

API_MI=$(terraform -chdir=infra/app output -raw api_identity_principal_id)
WORKER_MI=$(terraform -chdir=infra/app output -raw worker_identity_principal_id)

for MI in "$API_MI" "$WORKER_MI"; do
  az rest --method POST \
    --uri "https://graph.microsoft.com/v1.0/servicePrincipals/$MI/appRoleAssignments" \
    --body "{\"principalId\":\"$MI\",\"resourceId\":\"$GRAPH_SP_ID\",\"appRoleId\":\"$MAIL_SEND_ROLE_ID\"}"
done
```

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

## 3. Incident response

See `docs/security/THREAT_MODEL.md` §8 for OpenAI key compromise, session
hijack, malicious image, and admin-account compromise procedures.
