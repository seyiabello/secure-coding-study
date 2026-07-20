resource "azurerm_storage_account" "sa" {
  name                = local.sa_name
  resource_group_name = azurerm_resource_group.rg.name
  location            = azurerm_resource_group.rg.location

  account_tier             = "Standard"
  account_replication_type = "LRS"

  min_tls_version = "TLS1_2"

  tags = var.tags
}

# ChromaDB vector store — persists the CWE corpus between container restarts
resource "azurerm_storage_share" "chromadb" {
  name               = "chromadb"
  storage_account_id = azurerm_storage_account.sa.id
  quota              = 5
}

# Session logs — JSONL files written during data collection; survives container restarts
resource "azurerm_storage_share" "logs" {
  name               = "logs"
  storage_account_id = azurerm_storage_account.sa.id
  quota              = 2
}
