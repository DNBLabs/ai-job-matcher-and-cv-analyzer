# Blob Storage for encrypted CV PDFs. Public access fully disabled; reachable
# only through a private endpoint (CONTEXT.md §Network). Shared access keys
# disabled -> data-plane auth is AAD/MI only (CONTEXT.md §Runtime & IAM).
resource "azurerm_storage_account" "main" {
  name                = local.storage_account_name
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location

  account_tier             = "Standard"
  account_replication_type = "LRS"

  min_tls_version                   = "TLS1_2"
  allow_nested_items_to_be_public   = false
  shared_access_key_enabled         = false # AAD/MI only; no static keys
  public_network_access_enabled     = false # private endpoint only
  infrastructure_encryption_enabled = true

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

# Private endpoint for the blob subresource, resolved by the privatelink zone.
# Source: https://github.com/hashicorp/terraform-provider-azurerm/blob/main/website/docs/r/private_endpoint.html.markdown
resource "azurerm_private_endpoint" "blob" {
  name                = "pe-blob-${local.name_prefix}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  subnet_id           = azurerm_subnet.private_endpoints.id

  private_service_connection {
    name                           = "psc-blob"
    private_connection_resource_id = azurerm_storage_account.main.id
    is_manual_connection           = false
    subresource_names              = ["blob"]
  }

  private_dns_zone_group {
    name                 = "blob-dns"
    private_dns_zone_ids = [azurerm_private_dns_zone.blob.id]
  }

  tags = local.common_tags
}
