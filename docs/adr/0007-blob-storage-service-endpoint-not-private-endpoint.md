# ADR-0007: CV Blob Storage via Service Endpoint + Network ACL, not a Private Endpoint

## Status

Accepted (2026-06-16; during the first live provisioning of Task 29)

Amends CONTEXT.md §Network ("Blob Storage: public access disabled").

## Context

The CV blob storage account was originally configured private-endpoint-only:
`public_network_access_enabled = false` plus an `azurerm_private_endpoint` in the
`snet-pe` subnet (Task 26).

During the first real `terraform apply`, this proved unworkable for any apply run
**from outside the VNet**:

- The `azurerm` provider (v4.x) **polls the blob data-plane endpoint** when it
  creates a storage account (to apply `blob_properties`). With public network
  access disabled, that endpoint is unreachable from a developer laptop or a
  GitHub-hosted runner, so the apply fails (`waiting for the Blob Service to
  become available`).
- This breaks **both** a local operator apply **and the Task 29 deploy pipeline**,
  which runs `terraform apply` from a GitHub-hosted runner (also outside the VNet).

Key Vault already faced the identical "reachable to provision, locked at runtime"
problem and resolved it (keyvault.tf, ADR-era Task 26) with a **service endpoint +
deny-by-default network ACL**, explicitly *not* a private endpoint. The blob
account simply did not follow that established pattern.

## Decision

Bring CV blob storage in line with Key Vault:

- `public_network_access_enabled = true`, with `network_rules`:
  `default_action = "Deny"`, `bypass = ["AzureServices"]`, the **ACA subnet**
  allowed via its existing `Microsoft.Storage` service endpoint, and the
  **operator/CI IP** allowed via `operator_ip_rules` for out-of-band container and
  data management. (Storage `ip_rules` reject `/32`, so the CIDR suffix is
  stripped.)
- Remove the blob **private endpoint** and the `privatelink.blob` private DNS
  zone + VNet link. (`snet-pe` is left defined but unused.)
- `shared_access_key_enabled = false` is unchanged — data-plane auth stays
  **Azure AD / Managed Identity only**; the provider uses `storage_use_azuread =
  true`. No static keys anywhere.

## Consequences

**Positive**

- Both local applies and the Task 29 GitHub-hosted pipeline can provision and
  reconcile the account.
- Consistent with the Key Vault posture already accepted for this project.
- Runtime access is unchanged in spirit: deny-by-default, ACA subnet only (plus
  transient operator/CI IP), RBAC + MI for the data plane, no shared keys.

**Negative / accepted**

- The account has a **public endpoint** (deny-by-default) rather than no public
  endpoint. Exposure is limited to the allowlisted ACA subnet and the transient
  operator/CI IP; every data-plane call still requires Azure AD + an RBAC role
  (the worker is read-only on `cvs/`, the API read/write).
- Slightly less strict than private-endpoint isolation; judged an acceptable
  trade for a £75/mo portfolio deployment, matching the Key Vault decision.

## References

- CONTEXT.md §Network; keyvault.tf (the pattern being matched).
- ADR-0006 (zero-touch deploy — the pipeline this unblocks).
- storage.tf, network.tf, infra/app/versions.tf (`storage_use_azuread`).
