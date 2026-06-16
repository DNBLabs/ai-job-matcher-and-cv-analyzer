# Blob Storage for encrypted CV PDFs. Locked to the ACA subnet (service
# endpoint) plus optional operator IPs via a deny-by-default network ACL — the
# same posture as Key Vault (keyvault.tf), not a private endpoint. A private
# endpoint cannot be provisioned or managed by Terraform from outside the VNet
# (the provider polls the blob data plane on create), which broke both local
# applies and the Task 29 GitHub-hosted deploy pipeline. See ADR-0007.
# Shared access keys disabled -> data-plane auth is AAD/MI only.
resource "azurerm_storage_account" "main" {
  name                = local.storage_account_name
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location

  account_tier             = "Standard"
  account_replication_type = "LRS"

  min_tls_version                   = "TLS1_2"
  allow_nested_items_to_be_public   = false
  shared_access_key_enabled         = false # AAD/MI only; no static keys
  public_network_access_enabled     = true  # service-endpoint + ACL; not a private endpoint
  infrastructure_encryption_enabled = true

  # Deny by default; allow the ACA subnet (service endpoint) for runtime MI
  # access and the operator/CI IP for out-of-band container + data management.
  network_rules {
    default_action             = "Deny"
    bypass                     = ["AzureServices"]
    virtual_network_subnet_ids = [azurerm_subnet.aca.id]
    # Storage ip_rules reject /32; pass bare IPs (operator_ip_rules carries CIDRs).
    ip_rules = [for cidr in var.operator_ip_rules : replace(cidr, "/32", "")]
  }

  blob_properties {
    delete_retention_policy {
      days = 7
    }
  }

  tags = local.common_tags
}

# Container holding CV PDFs under the cvs/{user_id}/{uuid}.pdf key scheme.
resource "azurerm_storage_container" "cvs" {
  name                  = local.blob_container_name
  storage_account_id    = azurerm_storage_account.main.id
  container_access_type = "private"
}
