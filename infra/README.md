# Terraform infrastructure-as-code (Azure)

Two stacks:

| Stack | Path | Backend | Purpose |
|-------|------|---------|---------|
| **Bootstrap** | `infra/bootstrap/` | local | Creates the remote-state storage the app stack uses (Task 25). |
| **Application** | `infra/app/` | azurerm (remote) | ACA, Postgres, Service Bus, Blob, Key Vault, ACR (Task 26). |

All resources carry the FinOps-mandated tags: `project`, `env`, `owner`, `cost-center`
(CONTEXT.md §Tagging, `docs/finance/BUDGET.md`). Default region: `uksouth`.

## Bootstrap stack — one-time apply

The bootstrap stack uses a **local backend** by design: it provisions the storage
account that holds remote state, so it cannot itself live in remote state
(chicken-and-egg). Run it once per subscription.

**Prerequisites**

- Terraform `>= 1.9` (`azurerm ~> 4.0`).
- Azure CLI logged in: `az login`.
- An empty subscription, with `ARM_SUBSCRIPTION_ID` exported (required by azurerm v4):

  ```bash
  export ARM_SUBSCRIPTION_ID="$(az account show --query id -o tsv)"
  ```

**Apply**

```bash
cd infra/bootstrap
terraform init
terraform plan  -var "owner_email=<operator-email>"
terraform apply -var "owner_email=<operator-email>"
```

`owner_email` is the only required variable (feeds the `owner` tag). Everything
else defaults to the production values above; override with `-var` as needed.

The storage account name is `staijmstate<random>` — a random suffix keeps the
globally-scoped name unique. After apply, read the generated values:

```bash
terraform output app_stack_backend_config
```

**State of the bootstrap stack itself:** the local `terraform.tfstate` produced
here references only the state-storage resource IDs (no application secrets).
Keep it with the operator or commit it to a private location.

## Application stack — remote backend config

Paste the `terraform output app_stack_backend_config` value into
`infra/app/backend.tf`. It looks like:

```hcl
terraform {
  backend "azurerm" {
    resource_group_name  = "rg-ai-job-matcher-tfstate"
    storage_account_name = "staijmstate<random>"
    container_name       = "tfstate"
    key                  = "app.tfstate"
    use_azuread_auth     = true
  }
}
```

The state storage account has **shared access keys disabled**, so the backend
authenticates with Azure AD (`use_azuread_auth = true`) using your `az login`
identity (or the CI OIDC identity) — no static storage keys anywhere.

## CI verification (no Azure credentials)

The CI `terraform` job runs credential-free checks on every PR:

```bash
terraform fmt -check -recursive
terraform init -backend=false   # downloads providers, skips remote state
terraform validate
```

`terraform plan` requires Azure credentials and is run locally by the operator
during apply (above) — it is not part of the secret-free PR gate.

## Teardown

See `docs/finance/BUDGET.md` §Teardown: destroy the application stack first,
then the bootstrap stack.
